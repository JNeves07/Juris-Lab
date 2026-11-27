"""Coletor de arquivos JSONL locais (uma decisão por linha)."""
from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class ColetorJSONL:
    """Lê um arquivo `.jsonl` sem abrir conexões de rede."""

    def __init__(self, origem: str | Path):
        self.origem = Path(origem)

    def coletar(self) -> Iterator[dict[str, Any]]:
        """Produz um registro por linha válida; linhas inválidas viram `{}`."""
        with self.origem.open(encoding="utf-8") as arquivo:
            for numero, linha in enumerate(arquivo, 1):
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    registro = json.loads(linha)
                except json.JSONDecodeError:
                    print(f"linha {numero}: JSON inválido, ignorada", file=sys.stderr)
                    yield {}
                    continue
                if not isinstance(registro, dict):
                    print(f"linha {numero}: registro não é objeto, ignorada", file=sys.stderr)
                    yield {}
                    continue
                yield registro
