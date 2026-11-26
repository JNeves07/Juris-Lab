"""Autenticação JWT para os endpoints administrativos."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import config
from app.config import Settings

try:
    import jwt
except ImportError as exc:  # pragma: no cover - dependência obrigatória
    raise RuntimeError("PyJWT não instalado. Execute pip install -r requirements.txt") from exc

portador = HTTPBearer(auto_error=False, description="Token Bearer de POST /api/admin/token")


def criar_token(sub: str = "admin", minutos: int = 60, cfg: Settings | None = None) -> str:
    """Gera um token HS256 com emissor e expiração."""
    configuracao = cfg or config.settings
    agora = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": sub,
            "iat": agora,
            "exp": agora + timedelta(minutes=minutos),
            "iss": "jurislab",
        },
        configuracao.jwt_secret,
        algorithm="HS256",
    )


def validar_token(token: str, cfg: Settings | None = None) -> dict:
    """Valida assinatura, expiração e emissor do token."""
    configuracao = cfg or config.settings
    try:
        dados = jwt.decode(
            token,
            configuracao.jwt_secret,
            algorithms=["HS256"],
            issuer="jurislab",
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return dados


def exigir_admin(
    credenciais: HTTPAuthorizationCredentials | None = Depends(portador),
) -> dict:
    """Dependency que exige um Bearer token válido."""
    if not credenciais:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Informe o token Bearer.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return validar_token(credenciais.credentials)
