"""Armazenamento local SQLite compatível com o SQL usado pela API PostgreSQL.

A aplicação foi escrita para PostgreSQL + pgvector. Este módulo permite rodar o
projeto inteiro sem servidor de banco: ele traduz automaticamente os trechos
PostgreSQL-específicos (``%(nome)s``, ``%s``, ``::tipo``, ``ILIKE``, ``@@``,
``websearch_to_tsquery``, ``ANY``) para SQLite e registra funções equivalentes
para busca textual. As rotas e os testes não precisam conhecer o backend.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[2]
_PADRAO = RAIZ / "data" / "jurislab.sqlite3"

_named = re.compile(r"%\(([A-Za-z_][A-Za-z0-9_]*)\)s")
_cast = re.compile(r"::[A-Za-z_][A-Za-z0-9_]*")
_any = re.compile(r"=\s*ANY\(\s*:([A-Za-z_][A-Za-z0-9_]*)\s*\)", re.IGNORECASE)
_positional = re.compile(r"%s")
_ilike = re.compile(r"\bILIKE\b", re.IGNORECASE)
_nulls = re.compile(r"\s+NULLS\s+LAST\b", re.IGNORECASE)
_match = re.compile(
    r"([A-Za-z_][A-Za-z0-9_.]*)\s+@@\s+(websearch_to_tsquery\([^()]*\))", re.IGNORECASE
)
_escrita = re.compile(r"^\s*(INSERT|UPDATE|DELETE|REPLACE)\b", re.IGNORECASE)
_operadores = {"or", "and", "ou", "e"}

_conn: sqlite3.Connection | None = None
_caminho: Path | str | None = None
_trava = threading.RLock()


def dobrar(texto: Any) -> str:
    """Remove acentos e caixa para comparações determinísticas."""
    bruto = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(caractere for caractere in bruto if not unicodedata.combining(caractere)).casefold()


def _palavras(query: Any, *, normalizar: bool = True) -> list[str]:
    """Extrai termos positivos de uma consulta no estilo websearch."""
    limpo = re.sub(r"-\S+", " ", str(query or ""))
    limpo = limpo.replace('"', " ")
    return [
        dobrar(palavra) if normalizar else palavra
        for palavra in re.findall(r"[\wÀ-ÿ]+", limpo, flags=re.UNICODE)
        if palavra.casefold() not in _operadores
    ]


def _termos(query: Any) -> tuple[list[str], list[str], bool]:
    """Devolve (termos, exclusões, modo OU)."""
    bruto = str(query or "")
    exclusoes = [dobrar(item) for item in re.findall(r"-(\S+)", bruto)]
    return _palavras(bruto), exclusoes, bool(re.search(r"\bOR\b", bruto, re.IGNORECASE))


def _ts_query(_cfg: Any, query: Any) -> str:
    """Substitui ``websearch_to_tsquery`` mantendo a sintaxe legível."""
    return re.sub(r"\bou\b", "OR", str(query or ""), flags=re.IGNORECASE)


def _ts_match(busca: Any, query: Any) -> int:
    """Pontua 1 quando o documento satisfaz a consulta (inclui exclusões)."""
    texto = dobrar(busca)
    termos, exclusoes, usar_ou = _termos(query)
    if not termos:
        return 0
    encontrados = [termo for termo in termos if termo in texto]
    ok = any(encontrados) if usar_ou else len(encontrados) == len(termos)
    if ok and any(item in texto for item in exclusoes):
        ok = False
    return int(ok)


def _ts_rank(busca: Any, query: Any) -> float:
    """Ranking simples por ocorrência dos termos, limitado para estabilidade."""
    termos, _, _ = _termos(query)
    if not termos:
        return 0.0
    texto = dobrar(busca)
    return float(min(sum(texto.count(termo) for termo in termos), 50))


def _ts_headline(_cfg: Any, texto: Any, query: Any, _opcoes: Any = None) -> str:
    """Envolve as palavras encontradas em ``<mark>`` para o destaque no front."""
    original = str(texto or "")
    termos = sorted(set(_palavras(query, normalizar=False)), key=len, reverse=True)
    if not termos:
        return original[:400]
    padrao = re.compile("|".join(re.escape(termo) for termo in termos), re.IGNORECASE)
    destacado = padrao.sub(lambda encontrado: f"<mark>{encontrado.group(0)}</mark>", original)
    posicao = destacado.find("<mark>")
    if posicao > 240:
        destacado = "..." + destacado[posicao - 200 :]
    return destacado[:600]


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def traduzir(sql: str) -> str:
    """Converte o dialeto PostgreSQL usado nas rotas para SQLite."""
    resultado = _named.sub(r":\1", sql)
    resultado = _cast.sub("", resultado)
    resultado = _any.sub(r"IN (SELECT value FROM json_each(:\1))", resultado)
    resultado = _positional.sub("?", resultado)
    resultado = _ilike.sub("LIKE", resultado)
    resultado = _nulls.sub("", resultado)
    return _match.sub(r"ts_match(\1, \2)", resultado)


def _parametros(params: Any) -> Any:
    """Listas viram JSON (para ``json_each``) e objetos Jsonb viram texto."""
    if isinstance(params, Mapping):
        resultado: dict[str, Any] = {}
        for chave, valor in params.items():
            if isinstance(valor, (list, tuple, set)):
                resultado[chave] = json.dumps(list(valor), ensure_ascii=False)
            elif hasattr(valor, "__class__") and type(valor).__name__ == "Jsonb":
                resultado[chave] = json.dumps(getattr(valor, "value", valor), ensure_ascii=False, default=str)
            else:
                resultado[chave] = valor
        return resultado
    if isinstance(params, Sequence) and not isinstance(params, (str, bytes)):
        return tuple(params)
    return ()


DDL = """
CREATE TABLE IF NOT EXISTS tribunais (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sigla TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    ramo TEXT NOT NULL,
    uf TEXT
);
CREATE TABLE IF NOT EXISTS orgaos_julgadores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tribunal_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    UNIQUE (tribunal_id, nome)
);
CREATE TABLE IF NOT EXISTS decisoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tribunal_id INTEGER NOT NULL,
    orgao_julgador_id INTEGER,
    tipo TEXT NOT NULL DEFAULT 'acordao',
    numero_processo TEXT,
    numero_cnj TEXT,
    classe TEXT,
    relator TEXT,
    data_julgamento TEXT,
    data_publicacao TEXT,
    ementa TEXT,
    inteiro_teor TEXT,
    tese TEXT,
    legislacao_citada TEXT,
    fonte TEXT,
    fonte_id TEXT,
    fonte_url TEXT,
    hash_conteudo TEXT,
    status TEXT NOT NULL DEFAULT 'vigente',
    busca TEXT,
    coletado_em TEXT,
    UNIQUE (tribunal_id, fonte_id)
);
CREATE INDEX IF NOT EXISTS idx_decisoes_data ON decisoes (data_julgamento DESC);
CREATE INDEX IF NOT EXISTS idx_decisoes_status ON decisoes (status);
CREATE INDEX IF NOT EXISTS idx_decisoes_tribunal ON decisoes (tribunal_id);
CREATE TABLE IF NOT EXISTS favoritos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decisao_id INTEGER NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS pastas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    pai_id INTEGER
);
CREATE TABLE IF NOT EXISTS decisao_pasta (
    decisao_id INTEGER NOT NULL,
    pasta_id INTEGER NOT NULL,
    PRIMARY KEY (decisao_id, pasta_id)
);
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS decisao_tag (
    decisao_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (decisao_id, tag_id)
);
CREATE TABLE IF NOT EXISTS anotacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decisao_id INTEGER NOT NULL,
    texto TEXT NOT NULL,
    trecho TEXT,
    criada_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS relacoes_decisoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origem_id INTEGER NOT NULL,
    destino_id INTEGER NOT NULL,
    tipo TEXT NOT NULL,
    nota TEXT,
    UNIQUE (origem_id, destino_id, tipo)
);
CREATE TABLE IF NOT EXISTS buscas_salvas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    consulta TEXT NOT NULL DEFAULT '',
    filtros TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS historico_alteracoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decisao_id INTEGER NOT NULL,
    campo TEXT NOT NULL,
    alterado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS coletas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fonte TEXT NOT NULL,
    iniciada_em TEXT DEFAULT (datetime('now')),
    finalizada_em TEXT DEFAULT (datetime('now')),
    inseridas INTEGER NOT NULL DEFAULT 0,
    atualizadas INTEGER NOT NULL DEFAULT 0,
    ignoradas INTEGER NOT NULL DEFAULT 0,
    erros INTEGER NOT NULL DEFAULT 0
);
CREATE VIEW IF NOT EXISTS pg_class AS
SELECT 'decisoes' AS relname, (SELECT count(*) FROM decisoes) AS reltuples;
"""


def _registrar_funcoes(conexao: sqlite3.Connection) -> None:
    conexao.create_function("websearch_to_tsquery", 2, _ts_query)
    conexao.create_function("ts_match", 2, _ts_match)
    conexao.create_function("ts_rank_cd", 2, _ts_rank)
    conexao.create_function("ts_headline", 4, _ts_headline)
    conexao.create_function("left", 2, lambda texto, n: str(texto or "")[: int(n or 0)])
    conexao.create_function("now", 0, _agora)


def _semear(conexao: sqlite3.Connection) -> None:
    """Carrega tribunais e decisões fictícias de exemplo, se ainda não houver dados."""
    tribunais = RAIZ / "db" / "02_tribunais.sql"
    if tribunais.is_file():
        for instrucao in tribunais.read_text(encoding="utf-8").split(";"):
            if "INSERT INTO TRIBUNAIS" in instrucao.upper():
                conexao.execute(traduzir(instrucao))

    exemplo = RAIZ / "dados" / "exemplo.jsonl"
    if not exemplo.is_file() or conexao.execute("SELECT count(*) FROM decisoes").fetchone()[0]:
        return

    tribunal = conexao.execute("SELECT id FROM tribunais WHERE sigla='STJ'").fetchone()
    if tribunal is None:
        return
    tribunal_id = tribunal[0]
    inseridas = 0
    for linha in exemplo.read_text(encoding="utf-8").splitlines():
        try:
            bruto = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if not isinstance(bruto, dict) or not bruto.get("fonte_id"):
            continue
        ementa = bruto.get("ementa") or bruto.get("inteiro_teor") or ""
        conteudo = "\x1f".join(filter(None, [ementa, bruto.get("tese"), bruto.get("inteiro_teor")]))
        orgao = bruto.get("orgao_julgador")
        orgao_id = None
        if orgao:
            conexao.execute(
                "INSERT OR IGNORE INTO orgaos_julgadores (tribunal_id, nome) VALUES (?,?)",
                (tribunal_id, orgao),
            )
            orgao_id = conexao.execute(
                "SELECT id FROM orgaos_julgadores WHERE tribunal_id=? AND nome=?", (tribunal_id, orgao)
            ).fetchone()[0]
        conexao.execute(
            """INSERT OR IGNORE INTO decisoes (
                   tribunal_id, orgao_julgador_id, tipo, numero_processo, numero_cnj, classe,
                   relator, data_julgamento, data_publicacao, ementa, inteiro_teor, tese,
                   legislacao_citada, fonte, fonte_id, fonte_url, hash_conteudo, status,
                   busca, coletado_em
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'vigente',?,?)""",
            (
                tribunal_id,
                orgao_id,
                str(bruto.get("tipo") or "acordao"),
                bruto.get("numero_processo"),
                bruto.get("numero_cnj"),
                bruto.get("classe"),
                bruto.get("relator"),
                bruto.get("data_julgamento"),
                bruto.get("data_publicacao"),
                ementa,
                bruto.get("inteiro_teor"),
                bruto.get("tese"),
                json.dumps(bruto.get("legislacao_citada") or [], ensure_ascii=False),
                "Exemplo (fictício)",
                bruto["fonte_id"],
                bruto.get("fonte_url"),
                hashlib.sha256(conteudo.encode("utf-8")).hexdigest(),
                conteudo,
                _agora(),
            ),
        )
        inseridas += 1
    conexao.execute(
        """INSERT INTO coletas (fonte, iniciada_em, finalizada_em, inseridas)
           VALUES (?,?,?,?)""",
        ("Exemplo (fictício)", _agora(), _agora(), inseridas),
    )


def iniciar(caminho: Path | str | None = None, sementar: bool = True) -> None:
    """Abre (uma vez) a conexão local e cria o esquema e a base de exemplo."""
    global _conn, _caminho
    destino = Path(caminho) if caminho is not None else _PADRAO
    with _trava:
        if _conn is not None and str(_caminho) == str(destino):
            return
        if _conn is not None:
            _conn.close()
        destino.parent.mkdir(parents=True, exist_ok=True)
        conexao = sqlite3.connect(str(destino), check_same_thread=False, isolation_level=None)
        conexao.row_factory = sqlite3.Row
        if str(destino) != ":memory:":
            conexao.execute("PRAGMA journal_mode=WAL")
        conexao.execute("PRAGMA foreign_keys=ON")
        _registrar_funcoes(conexao)
        for instrucao in DDL.split(";"):
            if instrucao.strip():
                conexao.execute(instrucao)
        if sementar:
            _semear(conexao)
        _conn, _caminho = conexao, destino


def fechar() -> None:
    """Fecha a conexão local (seguro em qualquer estado)."""
    global _conn, _caminho
    with _trava:
        conexao, _conn, _caminho = _conn, None, None
        if conexao is not None:
            conexao.close()


def ativo() -> bool:
    return _conn is not None


def q(
    sql: str,
    params: Any = None,
    one: bool = False,
    write: bool = False,
) -> Any:
    """Executa SQL parametrizado no SQLite devolvendo dicionários."""
    with _trava:
        if _conn is None:
            iniciar()
        conexao = _conn
        assert conexao is not None
        consulta = traduzir(sql)
        valores = _parametros(params)
        cursor = conexao.execute(consulta, valores)
        if cursor.description is None:
            return None
        linhas = [dict(linha) for linha in cursor.fetchall()]
        return linhas[0] if linhas and one else (None if one else linhas)


def executar_muitos(sql: str, sequencia: list[tuple[Any, ...]]) -> int:
    """Executa um lote no SQLite e devolve o total de linhas alteradas."""
    with _trava:
        if _conn is None:
            iniciar()
        conexao = _conn
        assert conexao is not None
        antes = conexao.total_changes
        conexao.executemany(traduzir(sql), sequencia)
        return conexao.total_changes - antes
