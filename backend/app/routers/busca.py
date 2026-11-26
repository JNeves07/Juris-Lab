"""Endpoint de busca de decisões."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app import db, services
from app.config import settings

router = APIRouter()


@router.get("/api/busca")
def busca(
    q_: str = Query("", alias="q", description="Texto da busca (aceita aspas, OR e -exclusão)"),
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
    filtros = {
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
    try:
        sql_total, params_total = services.construir_contagem_busca(
            limite_contagem=settings.limite_contagem, **filtros
        )
        sql, params = services.construir_consulta_busca(
            ordem=ordem, pagina=pagina, por_pagina=por_pagina, **filtros
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    total_row = db.q(sql_total, params_total, one=True) or {}
    total, total_truncado = services.calcular_total(
        total_row.get("n"), settings.limite_contagem
    )
    itens = db.q(sql, params)
    return {
        "total": total,
        "total_truncado": total_truncado,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "itens": itens,
    }
