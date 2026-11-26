"""Importador genérico de decisões (JSONL ou CSV) para o banco.

Uso:
    python -m importador.importar --arquivo dados/exemplo.jsonl --tribunal STJ --fonte "STJ dados abertos"
    python -m importador.importar --arquivo export.csv --tribunal TJCE --fonte "TJCE portal" \
        --mapa dados/mapa_tjce.json --lote 2000
    python -m importador.importar --arquivo export.csv --tribunal STJ --fonte "Teste" --dry-run

O arquivo precisa (ou, via --mapa, é traduzido para) ter estes campos:
    fonte_id*, ementa*, numero_processo, classe, relator, orgao_julgador, tipo,
    data_julgamento, data_publicacao, inteiro_teor, tese, fonte_url, legislacao_citada

O que é feito:
  - COPY em massa para tabela temporária (rápido para milhões de linhas)
  - upsert: insere novas, atualiza só quando o hash do conteúdo mudou
  - alterações em ementa/tese ficam no histórico (trigger do banco)
  - registro da coleta na tabela `coletas`
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import psycopg

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://juris:juris_dev@localhost:5432/jurisprudencia"
)
LOTE_PADRAO = 5000
LOTE = LOTE_PADRAO  # mantido para compatibilidade com imports antigos

CNJ_RE = re.compile(r"(\d{7})-?(\d{2})\.?(\d{4})\.?(\d)\.?(\d{2})\.?(\d{4})")
TIPOS = {
    "acordao", "decisao_monocratica", "sumula", "sumula_vinculante",
    "repercussao_geral", "recurso_repetitivo", "iac", "irdr", "outro",
}

COLUNAS = [
    "fonte_id", "numero_processo", "numero_cnj", "classe", "relator", "orgao_julgador",
    "tipo", "data_julgamento", "data_publicacao", "ementa", "inteiro_teor", "tese",
    "legislacao_citada", "fonte_url", "hash_conteudo",
]
COLUNAS_SQL = ", ".join(COLUNAS)

CRIAR_STAGE = (
    "CREATE TEMP TABLE _stage (fonte_id text, numero_processo text, numero_cnj text, "
    "classe text, relator text, orgao_julgador text, tipo text, data_julgamento text, "
    "data_publicacao text, ementa text, inteiro_teor text, tese text, "
    "legislacao_citada text, fonte_url text, hash_conteudo text)"
)


def parse_data(valor):
    """Converte datas comuns em ISO (AAAA-MM-DD); retorna None se inválida."""
    if not valor:
        return None
    texto = str(valor).strip()[:10]
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    return None


def extrair_cnj(numero):
    """Extrai e normaliza o número CNJ de um texto."""
    if not numero:
        return None
    encontrado = CNJ_RE.search(str(numero))
    if not encontrado:
        return None
    return "{}-{}.{}.{}.{}.{}".format(*encontrado.groups())


def limpar(texto):
    """Remove NUL e espaços; devolve None para valor vazio."""
    if texto is None:
        return None
    limpo = str(texto).replace("\x00", "").strip()
    return limpo or None


def normalizar(bruto: dict, mapa: dict | None) -> dict | None:
    """Traduz uma linha bruta para o formato do banco. None se inválida."""
    if not isinstance(bruto, dict):
        return None
    reg = {campo: bruto.get(origem) for campo, origem in mapa.items()} if mapa else dict(bruto)

    fonte_id = limpar(reg.get("fonte_id"))
    ementa = limpar(reg.get("ementa"))
    inteiro_teor = limpar(reg.get("inteiro_teor"))
    if not fonte_id or not (ementa or inteiro_teor):
        return None

    tipo = (limpar(reg.get("tipo")) or "acordao").lower()
    if tipo not in TIPOS:
        tipo = "outro"

    legis = reg.get("legislacao_citada") or []
    if isinstance(legis, str):
        try:
            legis = json.loads(legis)
        except json.JSONDecodeError:
            legis = [item.strip() for item in legis.split(";") if item.strip()]

    numero = limpar(reg.get("numero_processo"))
    tese = limpar(reg.get("tese"))

    conteudo = "\x1f".join(filter(None, [ementa, tese, inteiro_teor]))
    return {
        "fonte_id": fonte_id,
        "numero_processo": numero,
        "numero_cnj": extrair_cnj(numero),
        "classe": limpar(reg.get("classe")),
        "relator": limpar(reg.get("relator")),
        "orgao_julgador": limpar(reg.get("orgao_julgador")),
        "tipo": tipo,
        "data_julgamento": parse_data(reg.get("data_julgamento")),
        "data_publicacao": parse_data(reg.get("data_publicacao")),
        "ementa": ementa,
        "inteiro_teor": inteiro_teor,
        "tese": tese,
        "legislacao_citada": json.dumps(legis, ensure_ascii=False),
        "fonte_url": limpar(reg.get("fonte_url")),
        "hash_conteudo": hashlib.sha256(conteudo.encode("utf-8")).hexdigest(),
    }


def ler_arquivo(caminho: str | Path):
    """Lê JSONL (uma linha por registro) ou CSV, ignorando linhas inválidas."""
    caminho = Path(caminho)
    if caminho.suffix.lower() == ".csv":
        with caminho.open(newline="", encoding="utf-8-sig") as arquivo:
            yield from csv.DictReader(arquivo)
        return

    with caminho.open(encoding="utf-8") as arquivo:
        for numero, linha in enumerate(arquivo, 1):
            linha = linha.strip()
            if not linha:
                continue
            try:
                registro = json.loads(linha)
            except json.JSONDecodeError:
                print(f"linha {numero}: JSON inválido, ignorada", file=sys.stderr)
                yield {}
                continue
            if not isinstance(registro, dict):
                print(f"linha {numero}: registro não é objeto, ignorada", file=sys.stderr)
                yield {}
                continue
            yield registro


def copiar_lote(conn, registros: list[dict]):
    """Carrega um lote na tabela temporária via COPY."""
    buf = io.StringIO()
    escritor = csv.writer(buf)
    for registro in registros:
        escritor.writerow(
            [registro[coluna] if registro[coluna] is not None else "\\N" for coluna in COLUNAS]
        )
    buf.seek(0)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE _stage")
        with cur.copy(
            f"COPY _stage ({COLUNAS_SQL}) FROM STDIN WITH (FORMAT csv, NULL '\\N')"
        ) as copia:
            copia.write(buf.read())


UPSERT = """
WITH novos_orgaos AS (
    INSERT INTO orgaos_julgadores (tribunal_id, nome)
    SELECT DISTINCT %(trib)s, orgao_julgador FROM _stage WHERE orgao_julgador IS NOT NULL
    ON CONFLICT (tribunal_id, nome) DO NOTHING
),
up AS (
    INSERT INTO decisoes (
        tribunal_id, orgao_julgador_id, tipo, numero_processo, numero_cnj, classe, relator,
        data_julgamento, data_publicacao, ementa, inteiro_teor, tese, legislacao_citada,
        fonte, fonte_id, fonte_url, hash_conteudo
    )
    SELECT %(trib)s, oj.id, s.tipo::tipo_decisao, s.numero_processo, s.numero_cnj, s.classe, s.relator,
           s.data_julgamento::date, s.data_publicacao::date, s.ementa, s.inteiro_teor, s.tese,
           s.legislacao_citada::jsonb, %(fonte)s, s.fonte_id, s.fonte_url, s.hash_conteudo
    FROM _stage s
    LEFT JOIN orgaos_julgadores oj ON oj.tribunal_id = %(trib)s AND oj.nome = s.orgao_julgador
    ON CONFLICT (tribunal_id, fonte_id) DO UPDATE SET
        orgao_julgador_id = EXCLUDED.orgao_julgador_id,
        tipo = EXCLUDED.tipo, numero_processo = EXCLUDED.numero_processo,
        numero_cnj = EXCLUDED.numero_cnj, classe = EXCLUDED.classe, relator = EXCLUDED.relator,
        data_julgamento = EXCLUDED.data_julgamento, data_publicacao = EXCLUDED.data_publicacao,
        ementa = EXCLUDED.ementa, inteiro_teor = EXCLUDED.inteiro_teor, tese = EXCLUDED.tese,
        legislacao_citada = EXCLUDED.legislacao_citada, fonte_url = EXCLUDED.fonte_url,
        hash_conteudo = EXCLUDED.hash_conteudo, coletado_em = now()
    WHERE decisoes.hash_conteudo <> EXCLUDED.hash_conteudo
    RETURNING (xmax = 0) AS inserida
)
SELECT count(*) FILTER (WHERE inserida) AS inseridas,
       count(*) FILTER (WHERE NOT inserida) AS atualizadas
FROM up
"""


def _dry_run(arquivo: Path, mapa: dict | None, tamanho_lote: int) -> None:
    """Normaliza e reporta sem abrir conexão com o banco."""
    validos = invalidos = duplicados = 0
    vistos: set[str] = set()
    for linhas, bruto in enumerate(ler_arquivo(arquivo), 1):
        registro = normalizar(bruto, mapa)
        if registro is None:
            invalidos += 1
        elif registro["fonte_id"] in vistos:
            duplicados += 1
        else:
            vistos.add(registro["fonte_id"])
            validos += 1
        if linhas % tamanho_lote == 0:
            print(
                f"  ... {linhas:,} linhas lidas, {validos:,} válidos, {invalidos:,} inválidos",
                flush=True,
            )
    print(
        f"Dry-run concluído: {validos:,} válidos, {duplicados:,} duplicados, "
        f"{invalidos:,} inválidos. Nada foi gravado.",
        flush=True,
    )


def gravar_local(
    registros: list[dict],
    tribunal: str,
    fonte: str,
    caminho: str | None = None,
) -> dict:
    """Faz o upsert no SQLite local (modo sem servidor de banco)."""
    from app import loja

    loja.iniciar(caminho, sementar=False)
    sigla = (tribunal or "").strip().upper()
    trib = loja.q("SELECT id FROM tribunais WHERE sigla=%s", (sigla,), one=True)
    if not trib:
        raise ValueError(f"Tribunal '{tribunal}' não existe em `tribunais`.")

    tribunal_id = trib["id"]
    inseridas = atualizadas = ignoradas = 0
    for registro in registros:
        if not registro:
            continue
        atual = loja.q(
            "SELECT hash_conteudo FROM decisoes WHERE tribunal_id=%s AND fonte_id=%s",
            (tribunal_id, registro["fonte_id"]),
            one=True,
        )
        orgao_id = None
        if registro["orgao_julgador"]:
            loja.q(
                "INSERT OR IGNORE INTO orgaos_julgadores (tribunal_id, nome) VALUES (%s,%s)",
                (tribunal_id, registro["orgao_julgador"]),
                write=True,
            )
            orgao = loja.q(
                "SELECT id FROM orgaos_julgadores WHERE tribunal_id=%s AND nome=%s",
                (tribunal_id, registro["orgao_julgador"]),
                one=True,
            )
            orgao_id = orgao["id"] if orgao else None

        loja.q(
            """INSERT INTO decisoes (
                   tribunal_id, orgao_julgador_id, tipo, numero_processo, numero_cnj, classe,
                   relator, data_julgamento, data_publicacao, ementa, inteiro_teor, tese,
                   legislacao_citada, fonte, fonte_id, fonte_url, hash_conteudo,
                   busca, coletado_em
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (tribunal_id, fonte_id) DO UPDATE SET
                   tipo=excluded.tipo, numero_processo=excluded.numero_processo,
                   numero_cnj=excluded.numero_cnj, classe=excluded.classe,
                   relator=excluded.relator, data_julgamento=excluded.data_julgamento,
                   data_publicacao=excluded.data_publicacao, ementa=excluded.ementa,
                   inteiro_teor=excluded.inteiro_teor, tese=excluded.tese,
                   legislacao_citada=excluded.legislacao_citada, fonte_url=excluded.fonte_url,
                   hash_conteudo=excluded.hash_conteudo, busca=excluded.busca,
                   coletado_em=excluded.coletado_em
               WHERE decisoes.hash_conteudo <> excluded.hash_conteudo""",
            (
                tribunal_id,
                orgao_id,
                registro["tipo"],
                registro["numero_processo"],
                registro["numero_cnj"],
                registro["classe"],
                registro["relator"],
                registro["data_julgamento"],
                registro["data_publicacao"],
                registro["ementa"],
                registro["inteiro_teor"],
                registro["tese"],
                registro["legislacao_citada"],
                fonte,
                registro["fonte_id"],
                registro["fonte_url"],
                registro["hash_conteudo"],
                "\x1f".join(
                    filter(
                        None,
                        [registro["ementa"], registro["tese"], registro["inteiro_teor"]],
                    )
                ),
                datetime.now().isoformat(timespec="seconds"),
            ),
            write=True,
        )
        alteradas = int((loja.q("SELECT changes() AS n", one=True) or {}).get("n", 0))
        if not alteradas:
            ignoradas += 1
        elif atual is None:
            inseridas += 1
        else:
            atualizadas += 1

    agora = datetime.now().isoformat(timespec="seconds")
    loja.q(
        """INSERT INTO coletas (fonte, iniciada_em, finalizada_em, inseridas, atualizadas, ignoradas)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (fonte, agora, agora, inseridas, atualizadas, ignoradas),
        write=True,
    )
    return {
        "inseridas": inseridas,
        "atualizadas": atualizadas,
        "ignoradas": ignoradas,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI de importação, com validação de arquivo e opção de simulação."""
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--arquivo", required=True, help="Arquivo .jsonl ou .csv")
    ap.add_argument("--tribunal", required=True, help="Sigla, ex.: STJ")
    ap.add_argument("--fonte", required=True, help="Nome da origem, ex.: 'STJ dados abertos'")
    ap.add_argument("--mapa", help="JSON {campo_banco: coluna_do_arquivo}")
    ap.add_argument("--lote", type=int, default=LOTE_PADRAO, help="Registros por carga (padrão: 5000)")
    ap.add_argument(
        "--modo",
        choices=("auto", "postgres", "sqlite"),
        default="auto",
        help="Destino dos dados (padrão: sqlite se JLS_MODE=sqlite, senão postgres)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Normaliza e reporta sem gravar")
    args = ap.parse_args(argv)

    if args.lote < 1:
        ap.error("--lote deve ser maior que zero")

    arquivo = Path(args.arquivo)
    if not arquivo.is_file():
        sys.exit(f"Arquivo não encontrado: {arquivo}")

    mapa = None
    if args.mapa:
        caminho_mapa = Path(args.mapa)
        if not caminho_mapa.is_file():
            sys.exit(f"Mapa não encontrado: {caminho_mapa}")
        with caminho_mapa.open(encoding="utf-8") as arquivo_mapa:
            mapa = json.load(arquivo_mapa)

    print(f"Lendo {arquivo} (lote={args.lote:,})...", flush=True)
    if args.dry_run:
        print("Dry-run: nenhuma alteração será gravada.", flush=True)
        _dry_run(arquivo, mapa, args.lote)
        return 0

    modo = args.modo
    if modo == "auto":
        modo = "sqlite" if os.environ.get("JLS_MODE", "").lower() == "sqlite" else "postgres"

    if modo == "sqlite":
        registros = [normalizar(bruto, mapa) for bruto in ler_arquivo(arquivo)]
        try:
            resultado = gravar_local(registros, args.tribunal, args.fonte, os.environ.get("JLS_DB_PATH"))
        except ValueError as exc:
            sys.exit(str(exc))
        print(
            "Concluído (SQLite): {inseridas:,} inseridas, {atualizadas:,} atualizadas, "
            "{ignoradas:,} inalteradas.".format(**resultado),
            flush=True,
        )
        return 0

    try:
        with psycopg.connect(DATABASE_URL, autocommit=False) as conn:
            row = conn.execute(
                "SELECT id FROM tribunais WHERE sigla = %s", (args.tribunal,)
            ).fetchone()
            if not row:
                sys.exit(f"Tribunal '{args.tribunal}' não existe em `tribunais`.")
            trib = row[0]

            coleta_id = conn.execute(
                "INSERT INTO coletas (fonte) VALUES (%s) RETURNING id", (args.fonte,)
            ).fetchone()[0]
            conn.execute(CRIAR_STAGE)
            conn.commit()

            ins = atu = ign = err = 0
            lote: list[dict] = []
            vistos: set[str] = set()

            def descarrega():
                nonlocal ins, atu, ign, lote, vistos
                if not lote:
                    return
                copiar_lote(conn, lote)
                resultado = conn.execute(
                    UPSERT, {"trib": trib, "fonte": args.fonte}
                ).fetchone()
                inseridas, atualizadas = resultado[0], resultado[1]
                ins += inseridas
                atu += atualizadas
                ign += len(lote) - inseridas - atualizadas  # já existentes e idênticos
                conn.commit()
                print(
                    f"  ... {ins:,} inseridas, {atu:,} atualizadas, "
                    f"{ign:,} inalteradas, {err:,} erros",
                    flush=True,
                )
                lote, vistos = [], set()

            for bruto in ler_arquivo(arquivo):
                registro = normalizar(bruto, mapa) if bruto else None
                if registro is None:
                    err += 1
                    continue
                if registro["fonte_id"] in vistos:  # duplicata dentro do mesmo lote
                    ign += 1
                    continue
                vistos.add(registro["fonte_id"])
                lote.append(registro)
                if len(lote) >= args.lote:
                    descarrega()
            descarrega()

            conn.execute(
                "UPDATE coletas SET finalizada_em=now(), inseridas=%s, atualizadas=%s, "
                "ignoradas=%s, erros=%s WHERE id=%s",
                (ins, atu, ign, err, coleta_id),
            )
            conn.commit()
            # Atualiza estatísticas para o planejador de consultas
            conn.autocommit = True
            conn.execute("ANALYZE decisoes")
    except psycopg.Error as exc:
        sys.exit(f"Erro de banco de dados: {exc}")

    print(
        f"Concluído: {ins:,} inseridas, {atu:,} atualizadas, "
        f"{ign:,} inalteradas, {err:,} com erro.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
