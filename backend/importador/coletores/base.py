"""Contrato mínimo para fontes locais de decisões."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Coletor(Protocol):
    """Fonte que produz registros brutos, sem acesso à rede."""

    def coletar(self) -> Iterable[dict[str, Any]]:
        """Itera sobre os registros brutos da fonte."""
        ...
