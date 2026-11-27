"""Endpoints de busca e exportação de decisões."""
from __future__ import annotations

import csv
import io
import re
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, Response

from app import config, db, services

router = APIRouter()

CABECALHOS_CSV = (
    "Número do processo", "Classe", "Tribunal", "Relator",
    "Data de julgamento", "Situação", "Ementa",
)
COLUNAS_EXPORT = (
    "numero_processo", "classe", "tribunal", "relator",
    "data_julgamento", "status", "ementa",
)


def _filtros(
    *,
    q_: str,
    tribunal: list[str] | None,
    ramo: str | None,
    tipo: str | None,
    relator: str | None,
    data_ini: date | None,
    data_fim: date | None,
    status: str | None,
    pasta_id: int | None,
    tag: str | None,
    favoritos: bool,
) -> dict[str, Any]:
    """Filtros compartilhados pela busca paginada e pela exportação."""
    return {
        "texto": q_,
        "tribunal": tribunal,
        "ramo": ramo,
        "tipo": tipo,
        "relator": relator,
        "data_ini": data_ini,
        "data_fim": data_fim,
        "status": status,
        "pasta_id": pasta_id,
        "tag": tag,
        "favoritos": favoritos,
    }


def _linha_exportacao(linha: dict[str, Any]) -> dict[str, str]:
    """Normaliza uma linha SQL para o mesmo formato em CSV e JSON."""
    ementa = re.sub(r"</?mark>", "", str(linha.get("ementa") or ""))
    ementa = re.sub(r"\s+", " ", ementa).strip()
    if len(ementa) > services.LIMITE_EMENTA_EXPORT:
        ementa = ementa[: services.LIMITE_EMENTA_EXPORT - 1].rstrip() + "…"
    return {
        "numero_processo": str(linha.get("numero_processo") or ""),
        "classe": str(linha.get("classe") or ""),
        "tribunal": str(linha.get("tribunal") or ""),
        "relator": str(linha.get("relator") or ""),
        "data_julgamento": str(linha.get("data_julgamento") or ""),
        "status": str(linha.get("status") or ""),
        "ementa": ementa,
    }


@router.get("/api/busca")
def busca(
    q_: str = Query("", alias="q", description='Texto da busca (aceita aspas, "OU"/"OR" e "-excluir")'),
    tribunal: list[str] | None = Query(None),  # noqa: B008 (padrão FastAPI)
    ramo: str | None = None,
    tipo: str | None = None,
    relator: str | None = None,
    data_ini: date | None = None,
    data_fim: date | None = None,
    status: str | None = None,
    pasta_id: int | None = None,
    tag: str | None = None,
    favoritos: bool = False,
    ordem: str = Query("relevancia", pattern="^(relevancia|data_desc|data_asc)$"),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
):
    """Busca paginada com filtros, mantendo o formato original da resposta."""
    filtros = _filtros(
        q_=q_, tribunal=tribunal, ramo=ramo, tipo=tipo, relator=relator,
        data_ini=data_ini, data_fim=data_fim, status=status, pasta_id=pasta_id,
        tag=tag, favoritos=favoritos,
    )
    try:
        sql_total, params_total = services.construir_contagem_busca(
            limite_contagem=config.settings.limite_contagem, **filtros
        )
        sql, params = services.construir_consulta_busca(
            ordem=ordem, pagina=pagina, por_pagina=por_pagina, **filtros
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    total_row = db.q(sql_total, params_total, one=True) or {}
    total, total_truncado = services.calcular_total(
        total_row.get("n"), config.settings.limite_contagem
    )
    itens = db.q(sql, params)
    return {
        "total": total,
        "total_truncado": total_truncado,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "itens": itens,
    }


@router.get("/api/busca/export")
def exportar(
    q_: str = Query("", alias="q", description="Mesmos filtros de /api/busca"),
    tribunal: list[str] | None = Query(None),  # noqa: B008 (padrão FastAPI)
    ramo: str | None = None,
    tipo: str | None = None,
    relator: str | None = None,
    data_ini: date | None = None,
    data_fim: date | None = None,
    status: str | None = None,
    pasta_id: int | None = None,
    tag: str | None = None,
    favoritos: bool = False,
    ordem: str = Query("data_desc", pattern="^(relevancia|data_desc|data_asc)$"),
    formato: Literal["csv", "json"] = Query("csv", description="csv ou json"),
):
    """Exporta até ``JLS_EXPORT_MAX`` decisões, sem paginação e sem cache."""
    filtros = _filtros(
        q_=q_, tribunal=tribunal, ramo=ramo, tipo=tipo, relator=relator,
        data_ini=data_ini, data_fim=data_fim, status=status, pasta_id=pasta_id,
        tag=tag, favoritos=favoritos,
    )
    try:
        sql, params = services.construir_consulta_busca(
            ordem=ordem, pagina=1, por_pagina=config.settings.export_max, **filtros
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    linhas = db.q(sql, params) or []
    registros = [_linha_exportacao(linha) for linha in linhas]
    nome_arquivo = f"jurislab-{date.today().isoformat()}.{formato}"
    cabecalhos = {
        "Content-Disposition": f'attachment; filename="{nome_arquivo}"',
        "Cache-Control": "no-store",
    }

    if formato == "json":
        return JSONResponse(registros, headers=cabecalhos)

    buf = io.StringIO()
    escritor = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    escritor.writerow(CABECALHOS_CSV)
    for registro in registros:
        escritor.writerow([registro[coluna] for coluna in COLUNAS_EXPORT])
    # BOM garante que planilhas Windows reconheçam o UTF-8 sem configuração.
    return Response(
        content="\ufeff" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers=cabecalhos,
    )
