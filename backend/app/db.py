"""Pool de conexões e funções simples de consulta ao PostgreSQL."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import settings

log = logging.getLogger(__name__)

Params = Mapping[str, Any] | Sequence[Any] | None
_pool: ConnectionPool | None = None


def criar_pool() -> ConnectionPool:
    """Cria o pool com `row_factory` de dicionário, como na API original."""
    return ConnectionPool(
        settings.database_url,
        min_size=settings.pool_min_size,
        max_size=settings.pool_max_size,
        kwargs={"row_factory": dict_row},
    )


def get_pool() -> ConnectionPool:
    """Retorna o pool ativo, criando-o sob demanda se necessário."""
    global _pool
    if _pool is None or getattr(_pool, "closed", False):
        _pool = criar_pool()
    return _pool


async def abrir() -> None:
    """Abre o pool no startup sem bloquear o event loop."""
    global _pool
    if _pool is None or getattr(_pool, "closed", False):
        _pool = await asyncio.to_thread(criar_pool)
        log.info("Pool de conexões iniciado")


async def fechar() -> None:
    """Fecha o pool no shutdown (seguro mesmo se nunca foi aberto)."""
    global _pool
    pool = _pool
    _pool = None
    if pool is not None and not getattr(pool, "closed", False):
        await asyncio.to_thread(pool.close)
        log.info("Pool de conexões fechado")


def q(
    sql: str,
    params: Params = None,
    one: bool = False,
    write: bool = False,
) -> Any:
    """Executa SQL parametrizado.

    Escrita com RETURNING devolve linhas; escrita sem RETURNING devolve None.
    Leitura devolve lista de dicionários, ou um dicionário quando `one=True`.
    """
    with get_pool().connection() as conn:
        cur = conn.execute(sql, params or ())
        if cur.description is None:
            if write:
                return None
            return None if one else []
        rows = cur.fetchall()
    return rows[0] if rows and one else (None if one else rows)
