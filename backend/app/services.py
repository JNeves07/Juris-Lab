"""Funções puras de construção de consultas e normalização de filtros."""
from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date
from typing import Any

CONFIG = "pt_unaccent"
LIMITE_CONTAGEM = 10_000
ORDENS_PERMITIDAS = ("relevancia", "data_desc", "data_asc")
IDENTIFICADOR_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
FROM_SQL = "FROM decisoes d JOIN tribunais t ON t.id = d.tribunal_id"
HEADLINE_OPTIONS = (
    "StartSel=<mark>, StopSel=</mark>, MaxFragments=2, MaxWords=45, MinWords=20"
)

Filtros = Mapping[str, Any]


def validar_identificador(valor: str, campo: str) -> str:
    """Valida enums/textos curtos em minúsculas, sem espaços ou acentos."""
    resultado = (valor or "").strip().lower()
    if not IDENTIFICADOR_RE.fullmatch(resultado):
        raise ValueError(
            f"{campo} inválido: use letras minúsculas, números e '_' (ex.: 'acordao')."
        )
    return resultado


def validar_ordem(ordem: str) -> str:
    """Normaliza e valida a ordem solicitada."""
    resultado = (ordem or "").strip().lower()
    if resultado not in ORDENS_PERMITIDAS:
        raise ValueError(
            "Ordem inválida: use 'relevancia', 'data_desc' ou 'data_asc'."
        )
    return resultado


def validar_periodo(data_ini: date | str | None, data_fim: date | str | None) -> None:
    """Rejeita intervalos com data inicial posterior à final."""
    if data_ini and data_fim and str(data_ini) > str(data_fim):
        raise ValueError("Data inicial não pode ser maior que a data final.")


def termo_para_like(texto: str) -> str:
    """Remove operadores da busca para casar metadados como número do processo."""
    limpo = re.sub(r"-\S+", " ", texto or "")
    limpo = limpo.replace('"', " ")
    limpo = re.sub(r"\b(?:or|and)\b", " ", limpo, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", limpo).strip()


def sql_headline(tem_texto: bool) -> str:
    """Expressão SQL do trecho destacado (com `<mark>` quando há busca)."""
    if tem_texto:
        return (
            "ts_headline(%(cfg)s::regconfig, coalesce(p.ementa,''), "
            "websearch_to_tsquery(%(cfg)s::regconfig, %(q)s), "
            f"'{HEADLINE_OPTIONS}')"
        )
    return "left(coalesce(p.ementa,''), 400)"


def definir_ordem(tem_texto: bool, ordem: str) -> tuple[str, str, str]:
    """Devolve (rank, ORDER BY da página, ORDER BY externo)."""
    if tem_texto and ordem == "relevancia":
        rank = (
            "ts_rank_cd(d.busca, websearch_to_tsquery(%(cfg)s::regconfig, %(q)s))"
        )
        return (
            rank,
            "ORDER BY rank DESC, d.data_julgamento DESC NULLS LAST",
            "ORDER BY rank DESC, p.data_julgamento DESC NULLS LAST",
        )
    if ordem == "data_asc":
        return (
            "0::real",
            "ORDER BY d.data_julgamento ASC NULLS LAST",
            "ORDER BY p.data_julgamento ASC NULLS LAST",
        )
    return (
        "0::real",
        "ORDER BY d.data_julgamento DESC NULLS LAST",
        "ORDER BY p.data_julgamento DESC NULLS LAST",
    )


def construir_filtros_busca(
    *,
    texto: str = "",
    tribunal: list[str] | tuple[str, ...] | None = None,
    ramo: str | None = None,
    tipo: str | None = None,
    relator: str | None = None,
    data_ini: date | str | None = None,
    data_fim: date | str | None = None,
    status: str | None = None,
    pasta_id: int | None = None,
    tag: str | None = None,
    favoritos: bool = False,
) -> tuple[list[str], dict[str, Any], bool]:
    """Constrói cláusulas WHERE e parâmetros; nenhum dado do usuário é concatenado."""
    validar_periodo(data_ini, data_fim)
    where = ["1=1"]
    params: dict[str, Any] = {"cfg": CONFIG}
    tem_texto = bool((texto or "").strip())

    if tem_texto:
        # O índice textual cobre ementa/tese/inteiro teor; metadados entram por LIKE
        # para que "REsp 1000001/SP" ou o nome do relator também encontrem a decisão.
        clausula = "d.busca @@ websearch_to_tsquery(%(cfg)s::regconfig, %(q)s)"
        termo_like = termo_para_like(texto)
        if termo_like:
            clausula = (
                f"({clausula} OR d.numero_processo ILIKE %(like_q)s"
                " OR d.numero_cnj ILIKE %(like_q)s"
                " OR d.classe ILIKE %(like_q)s"
                " OR d.relator ILIKE %(like_q)s)"
            )
            params["like_q"] = f"%{termo_like}%"
        where.append(clausula)
        params["q"] = texto
    if tribunal:
        where.append("t.sigla = ANY(%(tribunal)s)")
        params["tribunal"] = list(tribunal)
    if ramo:
        where.append("t.ramo = %(ramo)s")
        params["ramo"] = ramo
    if tipo:
        where.append("d.tipo = %(tipo)s::tipo_decisao")
        params["tipo"] = validar_identificador(tipo, "Tipo")
    if status:
        where.append("d.status = %(status)s::status_vigencia")
        params["status"] = validar_identificador(status, "Status")
    if relator:
        where.append("d.relator ILIKE %(relator)s")
        params["relator"] = f"%{relator}%"
    if data_ini:
        where.append("d.data_julgamento >= %(data_ini)s")
        params["data_ini"] = data_ini
    if data_fim:
        where.append("d.data_julgamento <= %(data_fim)s")
        params["data_fim"] = data_fim
    if pasta_id:
        where.append(
            "EXISTS (SELECT 1 FROM decisao_pasta dp "
            "WHERE dp.decisao_id = d.id AND dp.pasta_id = %(pasta_id)s)"
        )
        params["pasta_id"] = pasta_id
    if tag:
        where.append(
            "EXISTS (SELECT 1 FROM decisao_tag dt JOIN tags g ON g.id = dt.tag_id "
            "WHERE dt.decisao_id = d.id AND g.nome = %(tag)s)"
        )
        params["tag"] = tag
    if favoritos:
        where.append("EXISTS (SELECT 1 FROM favoritos f WHERE f.decisao_id = d.id)")

    return where, params, tem_texto


def construir_contagem_busca(
    *, limite_contagem: int = LIMITE_CONTAGEM, **filtros: Any
) -> tuple[str, dict[str, Any]]:
    """Conta até `limite_contagem + 1` para detectar resultados truncados."""
    where, params, _ = construir_filtros_busca(**filtros)
    params = dict(params)
    params["limite_contagem"] = limite_contagem + 1
    sql = (
        f"SELECT count(*) AS n FROM (SELECT 1 {FROM_SQL} "
        f"WHERE {' AND '.join(where)} LIMIT %(limite_contagem)s) s"
    )
    return sql, params


def construir_consulta_busca(
    *,
    ordem: str = "relevancia",
    pagina: int = 1,
    por_pagina: int = 20,
    **filtros: Any,
) -> tuple[str, dict[str, Any]]:
    """Monta a consulta paginada; headline é calculado depois da paginação."""
    ordem_validada = validar_ordem(ordem)
    if pagina < 1 or por_pagina < 1:
        raise ValueError("Paginação inválida: página e por_pagina devem ser >= 1.")

    where, params, tem_texto = construir_filtros_busca(**filtros)
    params = dict(params)
    params["limit"] = por_pagina
    params["offset"] = (pagina - 1) * por_pagina

    rank_sql, order_sql, order_pagina_sql = definir_ordem(tem_texto, ordem_validada)
    destaque_sql = sql_headline(tem_texto)
    where_sql = " AND ".join(where)

    sql = f"""
        WITH pagina AS (
            SELECT d.id, d.tipo, d.numero_processo, d.classe, d.relator, d.data_julgamento,
                   d.data_publicacao, d.ementa, d.status, t.sigla AS tribunal,
                   {rank_sql} AS rank
            {FROM_SQL}
            WHERE {where_sql}
            {order_sql}
            LIMIT %(limit)s OFFSET %(offset)s
        )
        SELECT p.id, p.tipo, p.numero_processo, p.classe, p.relator, p.data_julgamento,
               p.data_publicacao, p.status, p.tribunal, p.rank,
               {destaque_sql} AS trecho,
               EXISTS (SELECT 1 FROM favoritos f WHERE f.decisao_id = p.id) AS favorito
        FROM pagina p
        {order_pagina_sql}
    """
    return sql, params


def calcular_total(
    total: int | None, limite_contagem: int = LIMITE_CONTAGEM
) -> tuple[int, bool]:
    """Devolve (total exibido, truncado) a partir da contagem limitada."""
    numero = int(total or 0)
    truncado = numero > limite_contagem
    return (limite_contagem if truncado else numero), truncado
