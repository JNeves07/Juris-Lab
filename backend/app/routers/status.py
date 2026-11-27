"""Healthcheck e informações operacionais da instância."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import config, db

router = APIRouter()
log = logging.getLogger(__name__)
LIMITE_PROBE = 2.0


async def _consulta(sql: str) -> dict | None:
    """Executa uma consulta leve fora do event loop com limite de tempo."""
    return await asyncio.wait_for(
        asyncio.to_thread(db.q, sql, None, True), timeout=LIMITE_PROBE
    )


async def _banco_disponivel() -> bool:
    """Sonda o banco com ``SELECT 1`` sem expor detalhes da falha ao cliente."""
    try:
        linha = await _consulta("SELECT 1 AS ok")
    except Exception as exc:  # inclui TimeoutError do wait_for
        log.warning("Falha na sonda do banco: %s", exc)
        return False
    return bool(linha and linha.get("ok") == 1)


def _indisponivel() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"status": "indisponivel", "mensagem": "Banco de dados indisponível."},
    )


@router.get("/healthz", include_in_schema=False)
async def healthz():
    """Resposta mínima usada por Docker, Vercel e monitoramento."""
    if not await _banco_disponivel():
        return _indisponivel()
    return {"status": "ok"}


@router.get("/api/status")
async def status():
    """Detalhes do backend ativo, sem expor segredos nem contagem pesada."""
    if not await _banco_disponivel():
        return _indisponivel()
    try:
        linha = await _consulta(
            "SELECT reltuples::bigint AS n FROM pg_class WHERE relname='decisoes'"
        ) or {}
        total = linha.get("n")
        # reltuples = -1 sinaliza estatística desatualizada no PostgreSQL.
        if total is None or total < 0:
            total = (await _consulta("SELECT count(*) AS n FROM decisoes") or {}).get("n", 0)
    except Exception as exc:
        log.warning("Falha ao ler estatísticas do banco: %s", exc)
        return _indisponivel()
    return {
        "status": "ok",
        "versao": config.settings.versao,
        "modo": db.modo_ativo(),
        "decisoes": total,
        "documentacao": "/api/docs",
        "segredos_padrao": config.settings.secrets_padrao,
    }
