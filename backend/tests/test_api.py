"""Testes da API com `db.q` substituído por dublês (sem banco real)."""
from __future__ import annotations

import importlib
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import db


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    """Recarrega a app apontando para um front-end temporário."""
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<h1>Juris</h1>", encoding="utf-8")
    (frontend / "app.js").write_text("console.log('ok')", encoding="utf-8")
    monkeypatch.setenv("FRONTEND_DIR", str(frontend))

    import app.main as principal
    from app import config

    importlib.reload(config)
    importlib.reload(principal)
    monkeypatch.setattr(
        db, "q", lambda *args, **kwargs: None if kwargs.get("one") else []
    )
    return TestClient(principal.app)


def fake_q(respostas: list[tuple[str, Any]]):
    """Devolve o valor cuja chave aparece na SQL; padrão vazio/None."""

    def executar(sql, params=None, one=False, write=False):
        for trecho, valor in respostas:
            if trecho in sql:
                return valor
        return None if one else []

    return executar


def test_healthz(cliente):
    resposta = cliente.get("/healthz")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_busca_formato_e_truncamento(cliente, monkeypatch):
    monkeypatch.setattr(
        db, "q", fake_q([("SELECT count(*) AS n FROM (SELECT 1", {"n": 10001})])
    )
    resposta = cliente.get("/api/busca", params={"q": "dano moral", "por_pagina": 1})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["total"] == 10_000
    assert corpo["total_truncado"] is True
    assert corpo["pagina"] == 1
    assert corpo["por_pagina"] == 1
    assert corpo["itens"] == []


def test_busca_sem_truncamento(cliente, monkeypatch):
    monkeypatch.setattr(
        db, "q", fake_q([("SELECT count(*) AS n FROM (SELECT 1", {"n": 3})])
    )
    corpo = cliente.get("/api/busca").json()
    assert corpo["total"] == 3
    assert corpo["total_truncado"] is False


def test_busca_datas_invertidas_422(cliente):
    resposta = cliente.get(
        "/api/busca", params={"data_ini": "2024-05-01", "data_fim": "2024-04-01"}
    )
    assert resposta.status_code == 422
    assert "Data inicial" in resposta.json()["detail"]


def test_busca_tipo_invalido_422(cliente):
    resposta = cliente.get("/api/busca", params={"tipo": "TIPO INVÁLIDO"})
    assert resposta.status_code == 422
    assert "Tipo inválido" in resposta.json()["detail"]


def test_decisao_404(cliente):
    resposta = cliente.get("/api/decisoes/999")
    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Decisão não encontrada"


def test_decisao_completa(cliente, monkeypatch):
    monkeypatch.setattr(
        db,
        "q",
        fake_q(
            [
                ("SELECT d.*", {"id": 7, "busca": "x", "numero_processo": "0001"}),
                ("FROM anotacoes", [{"id": 1, "texto": "Anotação"}]),
                ("FROM tags g", [{"id": 2, "nome": "importante"}]),
                ("FROM pastas p", [{"id": 3, "nome": "Pasta"}]),
                ("FROM relacoes_decisoes r", [{"id": 4, "tipo": "cita"}]),
                ("FROM historico_alteracoes", [{"campo": "ementa"}]),
            ]
        ),
    )
    resposta = cliente.get("/api/decisoes/7")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "busca" not in corpo
    assert corpo["anotacoes"][0]["texto"] == "Anotação"
    assert corpo["tags"][0]["nome"] == "importante"
    assert corpo["pastas"][0]["nome"] == "Pasta"
    assert corpo["relacoes"][0]["tipo"] == "cita"
    assert corpo["historico"][0]["campo"] == "ementa"


def test_tribunais(cliente, monkeypatch):
    monkeypatch.setattr(
        db, "q", fake_q([("FROM tribunais", [{"id": 1, "sigla": "STJ"}])])
    )
    resposta = cliente.get("/api/tribunais")
    assert resposta.status_code == 200
    assert resposta.json() == [{"id": 1, "sigla": "STJ"}]


def test_estatisticas_fallback_reltuples(cliente, monkeypatch):
    chamadas: list[str] = []

    def executar(sql, params=None, one=False, write=False):
        chamadas.append(sql)
        if "reltuples" in sql:
            return {"n": -1}
        if "SELECT count(*) AS n FROM decisoes" in sql:
            return {"n": 42}
        if "GROUP BY t.sigla" in sql:
            return [{"sigla": "STJ", "n": 2}]
        if "FROM coletas" in sql:
            return [{"fonte": "STJ dados abertos"}]
        return None if one else []

    monkeypatch.setattr(db, "q", executar)
    corpo = cliente.get("/api/estatisticas").json()
    assert corpo["decisoes"] == 42
    assert corpo["por_tribunal"] == [{"sigla": "STJ", "n": 2}]
    assert corpo["ultima_coleta"][0]["fonte"] == "STJ dados abertos"
    assert any("count(*) AS n FROM decisoes" in sql for sql in chamadas)


def test_favorito_put_e_delete(cliente, monkeypatch):
    chamadas: list[tuple[str, bool]] = []

    def executar(sql, params=None, one=False, write=False):
        chamadas.append((sql, write))

    monkeypatch.setattr(db, "q", executar)
    assert cliente.put("/api/decisoes/5/favorito").json() == {"ok": True}
    assert cliente.delete("/api/decisoes/5/favorito").json() == {"ok": True}
    assert any("INSERT INTO favoritos" in sql and write for sql, write in chamadas)
    assert any("DELETE FROM favoritos" in sql and write for sql, write in chamadas)


def test_status_valido_e_invalido(cliente, monkeypatch):
    chamadas: list[str] = []

    def executar(sql, params=None, one=False, write=False):
        chamadas.append(sql)

    monkeypatch.setattr(db, "q", executar)
    resposta = cliente.put("/api/decisoes/5/status", json={"status": "revogada"})
    assert resposta.status_code == 200
    assert resposta.json() == {"ok": True}
    assert any("status_vigencia" in sql for sql in chamadas)

    invalida = cliente.put("/api/decisoes/5/status", json={"status": "INVÁLIDO"})
    assert invalida.status_code == 422
    assert "Status inválido" in invalida.json()["detail"][0]["msg"]


def test_pastas_criar_listar_apagar(cliente, monkeypatch):
    monkeypatch.setattr(
        db,
        "q",
        fake_q(
            [
                ("FROM pastas p", [{"id": 1, "nome": "Pasta", "pai_id": None}]),
                ("INSERT INTO pastas", [{"id": 2, "nome": "Nova", "pai_id": None}]),
            ]
        ),
    )
    assert cliente.get("/api/pastas").json()[0]["nome"] == "Pasta"
    criada = cliente.post("/api/pastas", json={"nome": "Nova"})
    assert criada.status_code == 200
    assert criada.json() == {"id": 2, "nome": "Nova", "pai_id": None}
    assert cliente.delete("/api/pastas/2").json() == {"ok": True}


def test_pasta_add_e_delete(cliente, monkeypatch):
    chamadas: list[tuple[str, bool]] = []

    def executar(sql, params=None, one=False, write=False):
        chamadas.append((sql, write))

    monkeypatch.setattr(db, "q", executar)
    assert cliente.put("/api/decisoes/5/pastas/9").json() == {"ok": True}
    assert cliente.delete("/api/decisoes/5/pastas/9").json() == {"ok": True}
    assert any("INSERT INTO decisao_pasta" in sql and write for sql, write in chamadas)
    assert any("DELETE FROM decisao_pasta" in sql and write for sql, write in chamadas)


def test_tags_add_listar_apagar(cliente, monkeypatch):
    monkeypatch.setattr(
        db,
        "q",
        fake_q(
            [
                ("FROM tags g", [{"id": 1, "nome": "urgente", "total": 2}]),
                ("INSERT INTO tags", [{"id": 8, "nome": "urgente"}]),
            ]
        ),
    )
    assert cliente.get("/api/tags").json()[0]["total"] == 2
    resposta = cliente.put("/api/decisoes/5/tags", json={"nome": " URGENTE "})
    assert resposta.status_code == 200
    assert resposta.json() == {"id": 8, "nome": "urgente"}
    assert cliente.delete("/api/decisoes/5/tags/8").json() == {"ok": True}


def test_tag_vazia_400(cliente):
    resposta = cliente.put("/api/decisoes/5/tags", json={"nome": "   "})
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Tag vazia"


def test_anotacoes_criar_apagar_e_limite(cliente, monkeypatch):
    monkeypatch.setattr(
        db,
        "q",
        fake_q(
            [
                (
                    "INSERT INTO anotacoes",
                    [{"id": 3, "texto": "Nota", "trecho": None, "criada_em": "2024-01-01"}],
                )
            ]
        ),
    )
    resposta = cliente.post("/api/decisoes/5/anotacoes", json={"texto": "Nota"})
    assert resposta.status_code == 200
    assert resposta.json()["id"] == 3
    assert cliente.delete("/api/anotacoes/3").json() == {"ok": True}

    longa = cliente.post(
        "/api/decisoes/5/anotacoes", json={"texto": "x" * 20_001}
    )
    assert longa.status_code == 422
    assert "máximo" in longa.json()["detail"][0]["msg"]


def test_relacoes_criar_apagar_e_tipo_invalido(cliente, monkeypatch):
    chamadas: list[tuple[str, bool]] = []

    def executar(sql, params=None, one=False, write=False):
        chamadas.append((sql, write))

    monkeypatch.setattr(db, "q", executar)
    resposta = cliente.post(
        "/api/decisoes/5/relacoes", json={"destino_id": 6, "tipo": "cita", "nota": "ver"}
    )
    assert resposta.status_code == 200
    assert resposta.json() == {"ok": True}
    assert cliente.delete("/api/relacoes/4").json() == {"ok": True}
    assert any("INSERT INTO relacoes_decisoes" in sql and write for sql, write in chamadas)

    invalida = cliente.post(
        "/api/decisoes/5/relacoes", json={"destino_id": 6, "tipo": "CITOU!"}
    )
    assert invalida.status_code == 422
    assert "Tipo de relação inválido" in invalida.json()["detail"][0]["msg"]


def test_buscas_salvas_criar_listar_apagar(cliente, monkeypatch):
    monkeypatch.setattr(
        db,
        "q",
        fake_q(
            [
                ("FROM buscas_salvas", [{"id": 1, "nome": "Salva", "consulta": "x", "filtros": {}}]),
                ("INSERT INTO buscas_salvas", [{"id": 2, "nome": "Nova"}]),
            ]
        ),
    )
    assert cliente.get("/api/buscas-salvas").json()[0]["nome"] == "Salva"
    resposta = cliente.post(
        "/api/buscas-salvas", json={"nome": "Nova", "consulta": "x", "filtros": {"ramo": "civel"}}
    )
    assert resposta.status_code == 200
    assert resposta.json() == {"id": 2, "nome": "Nova"}
    assert cliente.delete("/api/buscas-salvas/2").json() == {"ok": True}


def test_erro_422_padronizado(cliente):
    resposta = cliente.get("/api/busca", params={"pagina": 0})
    assert resposta.status_code == 422
    corpo = resposta.json()
    assert corpo["mensagem"] == "Dados inválidos. Confira os campos informados."
    assert isinstance(corpo["detail"], list)
    assert corpo["detail"][0]["campo"] == "pagina"
    assert "maior ou igual" in corpo["detail"][0]["msg"]


def test_estatico_index_e_arquivo(cliente):
    assert cliente.get("/").text == "<h1>Juris</h1>"
    resposta = cliente.get("/static/app.js")
    assert resposta.status_code == 200
    assert resposta.text == "console.log('ok')"


def test_lifespan_abre_e_fecha_pool(monkeypatch):
    chamadas: list[str] = []

    async def abrir():
        chamadas.append("abrir")

    async def fechar():
        chamadas.append("fechar")

    monkeypatch.setattr(db, "abrir", abrir)
    monkeypatch.setattr(db, "fechar", fechar)
    import app.main as principal

    with TestClient(principal.app) as cliente:
        assert cliente.get("/healthz").status_code == 200
    assert chamadas == ["abrir", "fechar"]
