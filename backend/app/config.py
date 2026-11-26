"""Configuração centralizada via variáveis de ambiente.

Nenhum segredo fica no código. Sem nenhuma variável definida, a aplicação usa
SQLite com dados de exemplo e está pronta para uso. Para produção, defina
``JLS_JWT_SECRET``, ``JLS_ADMIN_PASSWORD`` e (quando aplicável) ``DATABASE_URL``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATABASE_URL = "postgresql://juris:juris_dev@localhost:5432/jurisprudencia"
RAIZ = Path(__file__).resolve().parents[2]
FALLBACK_FRONTEND = Path("/app/frontend")
VERSAO = "1.1.0"


def _booleano(nome: str, padrao: bool = False) -> bool:
    return os.getenv(nome, "1" if padrao else "0").strip().lower() in {"1", "true", "yes", "on"}


def _inteiro(nome: str, padrao: int, minimo: int = 1) -> int:
    """Lê um inteiro positivo do ambiente, com valor seguro em caso de erro."""
    try:
        return max(minimo, int(os.environ.get(nome, padrao)))
    except (TypeError, ValueError):
        return padrao


def _frontend_dir() -> Path:
    """Resolve o diretório do front-end, preservando o fallback do container."""
    configurado = os.environ.get("FRONTEND_DIR")
    if configurado:
        caminho = Path(configurado)
        return caminho if caminho.exists() else FALLBACK_FRONTEND

    local = RAIZ / "frontend"
    return local if local.exists() else FALLBACK_FRONTEND


def _origens_cors() -> tuple[str, ...]:
    """Same-origin por padrão; use uma lista separada por vírgulas para liberar origens."""
    bruto = os.environ.get("JLS_CORS_ORIGINS", "")
    return tuple(item.strip() for item in bruto.split(",") if item.strip())


def _modo() -> str:
    modo = os.getenv("JLS_MODE", "").strip().lower()
    if modo in {"sqlite", "postgres"}:
        return modo
    # Com DATABASE_URL explícita o comportamento histórico (PostgreSQL) é mantido.
    return "postgres" if os.getenv("DATABASE_URL") else "sqlite"


def _caminho_banco() -> Path | str:
    configurado = os.getenv("JLS_DB_PATH")
    if configurado:
        return Path(configurado)
    if os.getenv("VERCEL"):
        return ":memory:"
    return RAIZ / "data" / "jurislab.sqlite3"


@dataclass(frozen=True)
class Settings:
    """Valores usados pela API, pelo banco e pelas validações."""

    modo: str
    database_url: str
    db_path: Path | str
    sementar: bool
    frontend_dir: Path
    cors_origins: tuple[str, ...]
    limite_contagem: int
    pool_min_size: int
    pool_max_size: int
    jwt_secret: str
    admin_password: str
    rate_limit: int
    rate_window: int
    max_nome: int
    max_texto: int
    max_trecho: int
    max_nota: int
    max_consulta: int
    versao: str = VERSAO

    @property
    def secrets_padrao(self) -> bool:
        """Indica que os segredos ainda são os de desenvolvimento."""
        return self.jwt_secret.startswith("dev-only-") or self.admin_password == "admin"

    @classmethod
    def from_env(cls) -> Settings:
        """Cria as configurações lendo o ambiente no momento da chamada."""
        return cls(
            modo=_modo(),
            database_url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
            db_path=_caminho_banco(),
            sementar=_booleano("JLS_SEED", True),
            frontend_dir=_frontend_dir(),
            cors_origins=_origens_cors(),
            limite_contagem=_inteiro("LIMITE_CONTAGEM", 10_000),
            pool_min_size=_inteiro("POOL_MIN_SIZE", 1),
            pool_max_size=_inteiro("POOL_MAX_SIZE", 10),
            jwt_secret=os.getenv("JLS_JWT_SECRET", "dev-only-jurislab-change-me-in-production"),
            admin_password=os.getenv("JLS_ADMIN_PASSWORD", "admin"),
            rate_limit=_inteiro("JLS_RATE_LIMIT", 10),
            rate_window=_inteiro("JLS_RATE_WINDOW", 60, 10),
            max_nome=_inteiro("MAX_NOME", 200),
            max_texto=_inteiro("MAX_TEXTO", 20_000),
            max_trecho=_inteiro("MAX_TRECHO", 4_000),
            max_nota=_inteiro("MAX_NOTA", 2_000),
            max_consulta=_inteiro("MAX_CONSULTA", 4_000),
        )


settings = Settings.from_env()
