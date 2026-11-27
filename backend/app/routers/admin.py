"""Endpoints administrativos protegidos por JWT."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException

from app import config, db
from app.schemas import ImportarIn, TokenIn
from app.security import criar_token, exigir_admin, segredos_permitidos

router = APIRouter()


@router.post("/api/admin/token")
def token(body: TokenIn) -> dict:
    """Troca a senha administrativa por um token Bearer de 60 minutos."""
    if not segredos_permitidos():
        raise HTTPException(503, "Segredos de desenvolvimento não autorizados nesta instância.")
    if not secrets.compare_digest(body.password, config.settings.admin_password):
        raise HTTPException(status_code=401, detail="Senha administrativa inválida.")
    return {"access_token": criar_token(), "token_type": "bearer", "expires_in": 3600}


@router.get("/api/admin/info")
def info(_: dict = Depends(exigir_admin)) -> dict:
    """Resumo da instância, incluindo o backend em uso."""
    return {
        "modo": db.modo_ativo(),
        "versao": config.settings.versao,
        "segredos_padrao": config.settings.secrets_padrao,
        "importacao_pela_api": db.modo_ativo() == "sqlite",
    }


@router.post("/api/admin/importar")
def importar(body: ImportarIn, _: dict = Depends(exigir_admin)) -> dict:
    """Importa um lote de decisões no SQLite local (use a CLI no PostgreSQL)."""
    if db.modo_ativo() != "sqlite":
        raise HTTPException(
            status_code=400,
            detail="Importação pela API disponível apenas no modo SQLite. Use a CLI do importador.",
        )
    from importador.importar import gravar_local, normalizar

    registros: list[dict] = []
    for bruto in body.registros:
        if not isinstance(bruto, dict):
            continue
        try:
            registro = normalizar(bruto, None)
        except Exception as exc:  # pragma: no cover - normalização é pura e validada
            raise HTTPException(status_code=422, detail=f"Registro inválido: {exc}") from exc
        if registro is None:
            raise HTTPException(422, "Cada registro precisa de fonte_id e ementa ou inteiro_teor.")
        registros.append(registro)

    try:
        return gravar_local(registros, body.tribunal, body.fonte, config.settings.db_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
