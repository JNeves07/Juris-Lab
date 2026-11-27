"""Testes das validações de enum que evitam erros 500 no banco."""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import db
from app.schemas import Relacao, StatusIn


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    """App com front-end temporário e `db.q` substituído por dublê."""
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<h1>Juris</h1>", encoding="utf-8")
    monkeypatch.setenv("FRONTEND_DIR", str(frontend))

    import app.main as principal
    from app import config

    importlib.reload(config)
    importlib.reload(principal)
    def consulta(sql, params=None, one=False, write=False):
        if one and "SELECT 1 AS ok" in sql:
            return {"ok": 1}
        return None if one else []

    monkeypatch.setattr(db, "q", consulta)
    return TestClient(principal.app)


def test_status_valido_e_normalizado():
    assert StatusIn(status="SUPERADA").status == "superada"


def test_status_invalido_e_rejeitado():
    with pytest.raises(ValidationError, match="Status inválido"):
        StatusIn(status="inexistente")


def test_tipo_relacao_valido():
    assert Relacao(destino_id=2, tipo="distingue").tipo == "distingue"


def test_tipo_relacao_invalido_e_rejeitado():
    with pytest.raises(ValidationError, match="Tipo de relação inválido"):
        Relacao(destino_id=2, tipo="inexistente")


def test_api_status_invalido_retorna_422(cliente):
    resposta = cliente.put("/api/decisoes/1/status", json={"status": "inexistente"})
    assert resposta.status_code == 422
    assert "Status inválido" in resposta.json()["detail"][0]["msg"]


def test_api_relacao_invalida_retorna_422(cliente):
    resposta = cliente.post(
        "/api/decisoes/1/relacoes", json={"destino_id": 2, "tipo": "inexistente"}
    )
    assert resposta.status_code == 422
    assert "Tipo de relação inválido" in resposta.json()["detail"][0]["msg"]


def test_api_relacao_consigo_mesmo_retorna_400(cliente):
    resposta = cliente.post(
        "/api/decisoes/1/relacoes", json={"destino_id": 1, "tipo": "cita"}
    )
    assert resposta.status_code == 400
    assert "consigo mesma" in resposta.json()["detail"]
