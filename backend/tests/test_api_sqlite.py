"""Testes ponta a ponta da aplicação no modo SQLite (sem banco externo)."""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from app import config, db, loja, main, security


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    """App real, com banco SQLite temporário e segredos de teste."""
    monkeypatch.setenv("JLS_MODE", "sqlite")
    monkeypatch.setenv("JLS_DB_PATH", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("JLS_JWT_SECRET", "segredo-de-teste-com-32-caracteres-ou-mais")
    monkeypatch.setenv("JLS_ADMIN_PASSWORD", "senha-de-teste")
    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(main)
    loja.fechar()
    with TestClient(main.app) as teste:
        yield teste
    loja.fechar()


def test_health_status_documentacao_e_interface(cliente):
    assert cliente.get("/healthz").json() == {"status": "ok"}
    status = cliente.get("/api/status").json()
    assert status["modo"] == "sqlite"
    assert status["decisoes"] == 5
    assert status["documentacao"] == "/api/docs"
    assert cliente.get("/api/docs").status_code == 200
    assert cliente.get("/").status_code == 200
    assert cliente.get("/static/js/app.js").status_code == 200


def test_busca_e_leitura_reais(cliente):
    resultado = cliente.get("/api/busca", params={"q": "dano moral"}).json()
    assert resultado["total"] == 2
    assert "<mark>" in resultado["itens"][0]["trecho"]

    metadado = cliente.get("/api/busca", params={"q": "REsp 1000001/SP"}).json()
    assert metadado["total"] == 1

    decisao = cliente.get("/api/decisoes/1").json()
    assert decisao["numero_processo"] == "REsp 1000001/SP"
    assert "busca" not in decisao

    assert len(cliente.get("/api/tribunais").json()) == 92
    assert cliente.get("/api/estatisticas").json()["decisoes"] == 5


def test_cabecalhos_de_seguranca(cliente):
    resposta = cliente.get("/api/status")
    assert resposta.headers["x-content-type-options"] == "nosniff"
    assert resposta.headers["x-frame-options"] == "DENY"
    assert resposta.headers["referrer-policy"] == "no-referrer"
    assert resposta.headers["cache-control"] == "no-store"
    assert "default-src" in resposta.headers["content-security-policy"]


def test_admin_token_e_importacao(cliente):
    assert cliente.post("/api/admin/token", json={"password": "errada"}).status_code == 401

    resposta = cliente.post("/api/admin/token", json={"password": "senha-de-teste"})
    assert resposta.status_code == 200
    token = resposta.json()["access_token"]
    cabecalho = {"Authorization": f"Bearer {token}"}

    assert cliente.get("/api/admin/info").status_code == 401
    info = cliente.get("/api/admin/info", headers=cabecalho).json()
    assert info["modo"] == "sqlite"
    assert info["importacao_pela_api"] is True

    importacao = cliente.post(
        "/api/admin/importar",
        headers=cabecalho,
        json={
            "registros": [
                {
                    "fonte_id": "NOVO-1",
                    "ementa": "Nova decisão sobre responsabilidade civil e dano moral.",
                    "numero_processo": "REsp 9999999/SP",
                    "tipo": "acordao",
                }
            ],
            "tribunal": "STJ",
            "fonte": "Teste da API",
        },
    )
    assert importacao.status_code == 200
    assert importacao.json()["inseridas"] == 1
    assert cliente.get("/api/busca", params={"q": "REsp 9999999/SP"}).json()["total"] == 1


def test_exportacao_real_csv_e_json(cliente):
    csv_resposta = cliente.get("/api/busca/export", params={"formato": "csv"})
    assert csv_resposta.status_code == 200
    assert csv_resposta.text.startswith("\ufeff")
    assert "REsp 1000001/SP" in csv_resposta.text

    json_resposta = cliente.get("/api/busca/export", params={"formato": "json"})
    registros = json_resposta.json()
    assert len(registros) == 5
    assert set(registros[0]) == {
        "numero_processo", "classe", "tribunal", "relator",
        "data_julgamento", "status", "ementa",
    }


def test_exportacao_com_filtro_invalido(cliente):
    resposta = cliente.get("/api/busca/export", params={"status": "inexistente"})
    assert resposta.status_code == 422


def test_status_e_healthz_com_banco_indisponivel(cliente, monkeypatch):
    def quebrado(*args, **kwargs):
        raise OSError("detalhe interno do banco")

    monkeypatch.setattr(db, "q", quebrado)
    for caminho in ("/healthz", "/api/status"):
        resposta = cliente.get(caminho)
        assert resposta.status_code == 503
        assert "detalhe interno" not in resposta.text


def test_importacao_pela_api_rejeita_itens_invalidos(cliente):
    token = cliente.post("/api/admin/token", json={"password": "senha-de-teste"}).json()["access_token"]
    cabecalho = {"Authorization": f"Bearer {token}"}

    invalido = cliente.post(
        "/api/admin/importar", headers=cabecalho,
        json={"registros": ["nao e objeto"], "tribunal": "STJ"},
    )
    assert invalido.status_code == 422

    gigante = cliente.post(
        "/api/admin/importar", headers=cabecalho,
        json={"registros": [{"fonte_id": "x", "ementa": "a" * 20_001}], "tribunal": "STJ"},
    )
    assert gigante.status_code == 422


def test_token_com_segredos_padrao_exige_autorizacao(cliente, monkeypatch):
    from dataclasses import replace

    padrao = replace(
        config.settings,
        jwt_secret="dev-only-jurislab-change-me-in-production",
        admin_password="admin",
        permitir_segredos_padrao=False,
    )
    monkeypatch.setattr(config, "settings", padrao)
    assert cliente.post("/api/admin/token", json={"password": "admin"}).status_code == 503

    monkeypatch.setattr(config, "settings", replace(padrao, permitir_segredos_padrao=True))
    resposta = cliente.post("/api/admin/token", json={"password": "admin"})
    assert resposta.status_code == 200
    assert security.validar_token(resposta.json()["access_token"], replace(
        padrao, permitir_segredos_padrao=True
    ))["aud"] == security.AUDIENCIA
