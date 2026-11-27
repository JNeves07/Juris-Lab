"""Testes da API com `db.q` substituído por dublês (sem banco real)."""
from __future__ import annotations

import importlib
from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app import config, db


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
    def consulta(sql, params=None, one=False, write=False):
        if one and "SELECT 1 AS ok" in sql:
            return {"ok": 1}
        if one and "reltuples" in sql:
            return {"n": 7}
        return None if one else []

    monkeypatch.setattr(db, "q", consulta)
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


def test_busca_repassa_texto_e_like_ao_banco(cliente, monkeypatch):
    chamadas: list[dict[str, Any]] = []

    def executar(sql, params=None, one=False, write=False):
        chamadas.append(dict(params or {}))
        return {"n": 1} if one and "count(*)" in sql else []

    monkeypatch.setattr(db, "q", executar)
    resposta = cliente.get("/api/busca", params={"q": "REsp 1000001/SP"})
    assert resposta.status_code == 200
    assert chamadas
    assert all(c["q"] == "REsp 1000001/SP" for c in chamadas)
    assert all(c["like_q"] == "%REsp 1000001/SP%" for c in chamadas)


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


def cliente_configurado(monkeypatch, tmp_path, **variaveis) -> tuple[TestClient, Any]:
    """Cria uma app isolada com variáveis de ambiente específicas."""
    frontend = tmp_path / "frontend"
    frontend.mkdir(exist_ok=True)
    (frontend / "index.html").write_text("<h1>Juris</h1>", encoding="utf-8")
    monkeypatch.setenv("FRONTEND_DIR", str(frontend))
    for chave, valor in variaveis.items():
        monkeypatch.setenv(chave, str(valor))

    import app.main as principal

    importlib.reload(config)
    importlib.reload(principal)
    return TestClient(principal.criar_app()), principal


def test_exportar_csv(cliente, monkeypatch):
    linha = {
        "numero_processo": "REsp 1/SP", "classe": "REsp", "tribunal": "STJ",
        "relator": "Ministro Exemplo", "data_julgamento": "2024-01-02",
        "status": "vigente", "ementa": "<mark>Dano</mark>   moral",
    }
    monkeypatch.setattr(db, "q", fake_q([("WITH pagina AS", [linha])]))
    resposta = cliente.get("/api/busca/export", params={"q": "dano", "formato": "csv"})

    assert resposta.status_code == 200
    assert resposta.content.startswith(b"\xef\xbb\xbf")
    assert 'attachment; filename="jurislab-' in resposta.headers["content-disposition"]
    assert resposta.headers["cache-control"] == "no-store"
    texto = resposta.content.decode("utf-8-sig")
    assert texto.splitlines()[0] == (
        '"Número do processo";"Classe";"Tribunal";"Relator";'
        '"Data de julgamento";"Situação";"Ementa"'
    )
    assert '"REsp 1/SP";"REsp";"STJ"' in texto
    assert "Dano moral" in texto
    assert "<mark>" not in texto


def test_exportar_json(cliente, monkeypatch):
    linha = {
        "numero_processo": "HC 2/CE", "classe": "HC", "tribunal": "STJ",
        "relator": "Ministra Exemplo", "data_julgamento": "2024-03-04",
        "status": "superada", "ementa": "x" * 1_500,
    }
    monkeypatch.setattr(db, "q", fake_q([("WITH pagina AS", [linha])]))
    resposta = cliente.get("/api/busca/export", params={"formato": "json"})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert isinstance(corpo, list) and len(corpo) == 1
    assert list(corpo[0]) == [
        "numero_processo", "classe", "tribunal", "relator",
        "data_julgamento", "status", "ementa",
    ]
    assert corpo[0]["ementa"].endswith("…")
    assert len(corpo[0]["ementa"]) == 1_000


def test_exportar_respeita_limite_configurado(cliente, monkeypatch):
    chamadas: list[dict[str, Any]] = []

    def executar(sql, params=None, one=False, write=False):
        chamadas.append(dict(params or {}))
        return [{}]

    monkeypatch.setattr(db, "q", executar)
    monkeypatch.setattr(config, "settings", replace(config.settings, export_max=2))
    resposta = cliente.get("/api/busca/export", params={"formato": "json"})
    assert resposta.status_code == 200
    assert chamadas[0]["limit"] == 2

    invalido = cliente.get("/api/busca/export", params={"formato": "xls"})
    assert invalido.status_code == 422


def test_busca_rejeita_enums_sintaticamente_validos(cliente):
    for campo in ("status", "tipo"):
        resposta = cliente.get("/api/busca", params={campo: "foo"})
        assert resposta.status_code == 422
        assert "inválido" in str(resposta.json()["detail"])


def test_sonda_de_banco_falha_sem_vazar_detalhes(cliente, monkeypatch):
    def quebrado(*args, **kwargs):
        raise RuntimeError("psycopg: senha=super-secreta-xyz")

    monkeypatch.setattr(db, "q", quebrado)
    for caminho in ("/healthz", "/api/status"):
        resposta = cliente.get(caminho)
        assert resposta.status_code == 503
        assert "super-secreta" not in resposta.text
        assert "Traceback" not in resposta.text


def test_limite_de_token_ignora_forwarded_for_padrao(monkeypatch, tmp_path):
    cliente, principal = cliente_configurado(
        monkeypatch, tmp_path,
        JLS_RATE_LIMIT=2, JLS_RATE_WINDOW=60, JLS_ALLOW_DEFAULT_SECRETS=1,
    )
    principal._hits.clear()
    corpo = {"password": "admin"}

    for _ in range(2):
        assert cliente.post(
            "/api/admin/token", json=corpo, headers={"x-forwarded-for": "203.0.113.9"}
        ).status_code == 200
    assert cliente.post("/api/admin/token", json=corpo).status_code == 429
    assert "203.0.113.9" not in principal._hits
    assert len(principal._hits) == 1


def test_limite_de_token_respeita_proxy_opt_in(monkeypatch, tmp_path):
    cliente, principal = cliente_configurado(
        monkeypatch, tmp_path,
        JLS_RATE_LIMIT=1, JLS_RATE_WINDOW=60,
        JLS_ALLOW_DEFAULT_SECRETS=1, JLS_TRUST_PROXY=1,
    )
    principal._hits.clear()
    corpo = {"password": "admin"}
    assert cliente.post(
        "/api/admin/token", json=corpo, headers={"x-forwarded-for": "203.0.113.1"}
    ).status_code == 200
    assert cliente.post(
        "/api/admin/token", json=corpo, headers={"x-forwarded-for": "203.0.113.2"}
    ).status_code == 200
    assert cliente.post(
        "/api/admin/token", json=corpo, headers={"x-forwarded-for": "203.0.113.1"}
    ).status_code == 429


def test_request_id_e_habilitado_por_configuracao(monkeypatch, tmp_path):
    cliente, _ = cliente_configurado(monkeypatch, tmp_path, JLS_REQUEST_ID=1)
    invalidado = cliente.get("/healthz", headers={"x-request-id": "nao-e-uuid"})
    assert str(UUID(invalidado.headers["x-request-id"])) == invalidado.headers["x-request-id"]

    enviado = "123e4567-e89b-12d3-a456-426614174000"
    repetido = cliente.get("/healthz", headers={"x-request-id": enviado})
    assert repetido.headers["x-request-id"] == enviado


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
