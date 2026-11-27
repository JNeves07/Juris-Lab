"""Fontes de coleta locais e mapeamento de registros."""
from __future__ import annotations

from importador.coletores.base import Coletor
from importador.coletores.jsonl import ColetorJSONL
from importador.coletores.mapeador import normalizar_registro

__all__ = ["Coletor", "ColetorJSONL", "normalizar_registro"]
