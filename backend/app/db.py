"""Camada de acesso a dados: PostgreSQL em produção, SQLite sem configuração.

As rotas continuam escrevendo a mesma SQL parametrizada. Aqui apenas escolhemos
o backend ativo e expomos ``q()``, ``abrir()``, ``fechar()`` e ``jsonb()``.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any

from app import config, loja

log = logging.getLogger(__name__)

Params = Mapping[str, Any] | Sequence[Any] | None
_pool: Any = None


def modo_ativo() -> str:
    """Nome do backend em uso (``sqlite`` ou ``postgres``)."""
    return config.settings.modo


def criar_pool() -> Any:
    """Cria o pool do PostgreSQL com ``row_factory`` de dicionário."""
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    return ConnectionPool(
        config.settings.database_url,
        min_size=config.settings.pool_min_size,
        max_size=config.settings.pool_max_size,
        kwargs={"row_factory": dict_row},
    )


def get_pool() -> Any:
    """Retorna o pool ativo, criando-o sob demanda se necessário."""
    global _pool
    if _pool is None or getattr(_pool, "closed", False):
        _pool = criar_pool()
    return _pool


async def abrir() -> None:
    """Prepara o backend no startup sem bloquear o event loop."""
    global _pool
    if config.settings.modo == "sqlite":
        await asyncio.to_thread(loja.iniciar, config.settings.db_path, config.settings.sementar)
        log.info("SQLite local pronto em %s", config.settings.db_path)
        return
    if _pool is None or getattr(_pool, "closed", False):
        _pool = await asyncio.to_thread(criar_pool)
        log.info("Pool de conexões iniciado")


async def fechar() -> None:
    """Encerra o backend no shutdown (seguro mesmo se nunca foi aberto)."""
    global _pool
    if config.settings.modo == "sqlite":
        await asyncio.to_thread(loja.fechar)
        return
    pool, _pool = _pool, None
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
    Leitura devolve lista de dicionários, ou um dicionário quando ``one=True``.
    """
    if config.settings.modo == "sqlite":
        return loja.q(sql, params, one=one, write=write)
    with get_pool().connection() as conn:
        cur = conn.execute(sql, params or ())
        if cur.description is None:
            return None
        rows = cur.fetchall()
    return rows[0] if rows and one else (None if one else rows)


def jsonb(valor: Any) -> Any:
    """Valor JSON no formato aceito pelo backend ativo."""
    if config.settings.modo == "sqlite":
        return json.dumps(valor, ensure_ascii=False, default=str)
    from psycopg.types.json import Jsonb

    return Jsonb(valor)
