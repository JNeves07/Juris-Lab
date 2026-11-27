"""Tradução de registros arbitrários para os campos aceitos pelo importador."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

CAMPOS_IMPORTADOR = (
    "fonte_id", "numero_processo", "numero_cnj", "classe", "relator",
    "orgao_julgador", "tipo", "data_julgamento", "data_publicacao", "ementa",
    "inteiro_teor", "tese", "legislacao_citada", "fonte_url",
)


def normalizar_registro(
    registro: Any, mapa: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Mapeia chaves de origem (com apoio a caminhos ``chave.subchave``).

    Sem mapa, devolve apenas os campos conhecidos pelo importador. Com mapa,
    ``{campo_do_importador: caminho_na_origem}`` seleciona valores arbitrários.
    """
    if not isinstance(registro, Mapping):
        return {}
    if not mapa:
        return {chave: registro[chave] for chave in CAMPOS_IMPORTADOR if chave in registro}

    resultado: dict[str, Any] = {}
    for destino, origem in mapa.items():
        if not isinstance(destino, str) or not isinstance(origem, str):
            continue
        valor: Any = registro
        for parte in origem.split("."):
            if not isinstance(valor, Mapping):
                valor = None
                break
            valor = valor.get(parte)
        if valor is not None:
            resultado[destino] = valor
    return resultado
