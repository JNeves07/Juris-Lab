"""Autenticação JWT para os endpoints administrativos."""
from __future__ import annotations

import re
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
AUDIENCIA = "juris-lab"
EMISSOR = "jurislab"
SUB_RE = re.compile(r"^[A-Za-z0-9._@-]{1,100}$")


def segredos_permitidos(cfg: Settings | None = None) -> bool:
    """Segredos padrão exigem autorização explícita para emissão e validação."""
    return (cfg or config.settings).segredos_utilizaveis


def validar_sub(sub: object) -> str:
    """Aceita apenas identificadores curtos e simples como sujeito do token."""
    if not isinstance(sub, str) or not SUB_RE.fullmatch(sub.strip()):
        raise ValueError("Sujeito do token inválido.")
    return sub.strip()


def criar_token(sub: str = "admin", minutos: int = 60, cfg: Settings | None = None) -> str:
    """Gera um token HS256 com sujeito, audiência, emissor e expiração."""
    configuracao = cfg or config.settings
    if not configuracao.segredos_utilizaveis:
        raise RuntimeError("Segredos de desenvolvimento exigem autorização explícita.")
    assunto = validar_sub(sub)
    agora = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": assunto,
            "iat": agora,
            "exp": agora + timedelta(minutes=minutos),
            "iss": EMISSOR,
            "aud": AUDIENCIA,
        },
        configuracao.jwt_secret,
        algorithm="HS256",
    )


def validar_token(token: str, cfg: Settings | None = None) -> dict:
    """Valida assinatura, expiração, emissor, audiência e sujeito do token."""
    configuracao = cfg or config.settings
    if not configuracao.segredos_utilizaveis:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        dados = jwt.decode(
            token,
            configuracao.jwt_secret,
            algorithms=["HS256"],
            audience=AUDIENCIA,
            issuer=EMISSOR,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
        validar_sub(dados.get("sub"))
    except (jwt.PyJWTError, ValueError) as exc:
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
