"""Modelos Pydantic do corpo das requisições."""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.services import validar_identificador

STATUS_PERMITIDOS = ("vigente", "superada", "revogada", "desconhecido")
TIPOS_RELACAO = (
    "segue", "cita", "distingue", "supera", "superada_por", "confirma", "contraria"
)


def validar_enum(valor: str, permitidos: tuple[str, ...], campo: str) -> str:
    """Normaliza e garante que o valor pertence ao enum do banco."""
    resultado = validar_identificador(valor, campo)
    if resultado not in permitidos:
        opcoes = ", ".join(permitidos)
        raise ValueError(f"{campo} inválido: use um destes valores: {opcoes}.")
    return resultado


class Nome(BaseModel):
    """Nome de pasta ou tag, com pai opcional."""

    nome: str = Field(min_length=1, max_length=settings.max_nome)
    pai_id: int | None = Field(default=None, ge=1)


class Texto(BaseModel):
    """Anotação de decisão, com trecho opcional."""

    texto: str = Field(min_length=1, max_length=settings.max_texto)
    trecho: str | None = Field(default=None, max_length=settings.max_trecho)


class Relacao(BaseModel):
    """Relacionamento entre decisões."""

    destino_id: int = Field(ge=1)
    tipo: str = Field(max_length=40)
    nota: str | None = Field(default=None, max_length=settings.max_nota)

    @field_validator("tipo")
    @classmethod
    def validar_tipo(cls, valor: str) -> str:
        return validar_enum(valor, TIPOS_RELACAO, "Tipo de relação")


class StatusIn(BaseModel):
    """Atualização de situação de vigência."""

    status: str = Field(max_length=40)

    @field_validator("status")
    @classmethod
    def validar_status(cls, valor: str) -> str:
        return validar_enum(valor, STATUS_PERMITIDOS, "Status")


class BuscaSalva(BaseModel):
    """Consulta salva pelo usuário."""

    nome: str = Field(min_length=1, max_length=settings.max_nome)
    consulta: str = Field(default="", max_length=settings.max_consulta)
    filtros: dict[str, Any] = Field(default_factory=dict)

    @field_validator("filtros")
    @classmethod
    def limitar_filtros(cls, valor: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(valor, ensure_ascii=False, default=str)) > settings.max_consulta:
            raise ValueError("Filtros muito grandes.")
        return valor


class TokenIn(BaseModel):
    """Senha administrativa usada para obter um JWT."""

    password: str = Field(min_length=1, max_length=200)


class ImportarIn(BaseModel):
    """Lote de decisões enviado pela API administrativa."""

    registros: list[dict[str, Any]] = Field(min_length=1, max_length=1000)
    tribunal: str = Field(default="STJ", max_length=10)
    fonte: str = Field(default="Importação pela API", max_length=200)
