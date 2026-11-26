"""Healthcheck e informações operacionais da instância."""
from __future__ import annotations

from fastapi import APIRouter

from app import config, db

router = APIRouter()


@router.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    """Resposta mínima usada por Docker, Vercel e monitoramento."""
    return {"status": "ok"}


@router.get("/api/status")
def status() -> dict:
    """Detalhes do backend ativo, sem expor segredos."""
    linha = db.q("SELECT count(*) AS n FROM decisoes", one=True) or {}
    return {
        "status": "ok",
        "versao": config.settings.versao,
        "modo": db.modo_ativo(),
        "decisoes": linha.get("n", 0),
        "documentacao": "/api/docs",
        "segredos_padrao": config.settings.secrets_padrao,
    }
