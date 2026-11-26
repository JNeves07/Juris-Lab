"""Configuração da aplicação a partir de variáveis de ambiente."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DATABASE_URL = "postgresql://juris:juris_dev@localhost:5432/jurisprudencia"
FALLBACK_FRONTEND = Path("/app/frontend")


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

    local = Path(__file__).resolve().parents[2] / "frontend"
    return local if local.exists() else FALLBACK_FRONTEND


def _origens_cors() -> list[str]:
    """Lista de origens permitidas; `*` mantém o comportamento padrão atual."""
    bruto = os.environ.get("CORS_ORIGINS", "*")
    origens = [item.strip() for item in bruto.split(",") if item.strip()]
    return origens or ["*"]


@dataclass(frozen=True)
class Settings:
    """Valores usados pela API, pelo pool e pelas validações."""

    database_url: str = DEFAULT_DATABASE_URL
    frontend_dir: Path = field(default_factory=_frontend_dir)
    cors_origins: list[str] = field(default_factory=_origens_cors)
    limite_contagem: int = 10_000
    pool_min_size: int = 1
    pool_max_size: int = 10
    max_nome: int = 200
    max_texto: int = 20_000
    max_trecho: int = 4_000
    max_nota: int = 2_000
    max_consulta: int = 4_000

    @classmethod
    def from_env(cls) -> Settings:
        """Cria as configurações lendo o ambiente no momento da chamada."""
        return cls(
            database_url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
            frontend_dir=_frontend_dir(),
            cors_origins=_origens_cors(),
            limite_contagem=_inteiro("LIMITE_CONTAGEM", 10_000),
            pool_min_size=_inteiro("POOL_MIN_SIZE", 1),
            pool_max_size=_inteiro("POOL_MAX_SIZE", 10),
            max_nome=_inteiro("MAX_NOME", 200),
            max_texto=_inteiro("MAX_TEXTO", 20_000),
            max_trecho=_inteiro("MAX_TRECHO", 4_000),
            max_nota=_inteiro("MAX_NOTA", 2_000),
            max_consulta=_inteiro("MAX_CONSULTA", 4_000),
        )


settings = Settings.from_env()
