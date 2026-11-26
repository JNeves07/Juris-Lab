"""Testes do modo SQLite: tradução de SQL, carga inicial e operações da API."""
from __future__ import annotations

import importlib
import json

import pytest

from app import config, db, loja, services


@pytest.fixture
def local(tmp_path, monkeypatch):
    """Banco SQLite isolado com os dados de exemplo."""
    monkeypatch.setenv("JLS_MODE", "sqlite")
    monkeypatch.setenv("JLS_DB_PATH", str(tmp_path / "juris.sqlite3"))
    importlib.reload(config)
    loja.fechar()
    loja.iniciar(config.settings.db_path, config.settings.sementar)
    yield
    loja.fechar()


def test_traduzir_parametros_e_operadores():
    sql = (
        "SELECT %(cfg)s::regconfig, %s FROM decisoes d "
        "WHERE d.busca @@ websearch_to_tsquery(%(cfg)s::regconfig, %(q)s) "
        "AND t.sigla = ANY(%(tribunal)s) AND d.relator ILIKE %(relator)s "
        "ORDER BY d.data_julgamento DESC NULLS LAST"
    )
    traduzido = loja.traduzir(sql)
    assert "SELECT :cfg, ? FROM decisoes d" in traduzido
    assert "ts_match(d.busca, websearch_to_tsquery(:cfg, :q))" in traduzido
    assert "IN (SELECT value FROM json_each(:tribunal))" in traduzido
    assert "ILIKE" not in traduzido
    assert "NULLS LAST" not in traduzido
    assert "::" not in traduzido


def test_semente_base_exemplo(local):
    assert db.q("SELECT count(*) AS n FROM tribunais", one=True)["n"] == 92
    assert db.q("SELECT count(*) AS n FROM decisoes", one=True)["n"] == 5
    assert db.q("SELECT count(*) AS n FROM coletas", one=True)["n"] == 1


def test_busca_por_texto_com_destaque(local):
    sql, params = services.construir_consulta_busca(texto="dano moral")
    itens = db.q(sql, params)
    assert len(itens) == 2
    assert all("<mark>" in item["trecho"] for item in itens)
    assert itens[0]["numero_processo"] == "REsp 1000001/SP"


def test_busca_por_metadado(local):
    sql, params = services.construir_consulta_busca(texto="REsp 1000001/SP")
    assert [item["numero_processo"] for item in db.q(sql, params)] == ["REsp 1000001/SP"]


def test_busca_aceita_ou_e_exclusao(local):
    assert loja._ts_match("dano moral", "dano OR inexistente") == 1
    assert loja._ts_match("dano moral", "dano -moral") == 0
    sql, params = services.construir_consulta_busca(texto="dano ou prejuízo")
    assert db.q(sql, params)


def test_filtro_tribunal_por_lista(local):
    linhas = db.q(
        "SELECT sigla FROM tribunais WHERE sigla = ANY(%(tribunal)s) ORDER BY sigla",
        {"tribunal": ["STJ", "TST"]},
    )
    assert [linha["sigla"] for linha in linhas] == ["STJ", "TST"]


def test_view_de_estatisticas(local):
    assert db.q("SELECT reltuples AS n FROM pg_class WHERE relname='decisoes'", one=True)["n"] == 5


def test_jsonb_no_sqlite(local):
    assert json.loads(db.jsonb({"ramo": "civel"})) == {"ramo": "civel"}


def test_crud_de_organizacao_no_sqlite(local):
    pasta = db.q("INSERT INTO pastas (nome, pai_id) VALUES (%s,%s) RETURNING id, nome, pai_id", ("Resumo", None))[0]
    assert db.q("SELECT nome FROM pastas WHERE id=%s", (pasta["id"],), one=True)["nome"] == "Resumo"

    tag = db.q(
        "INSERT INTO tags (nome) VALUES (%s) ON CONFLICT (nome) DO UPDATE SET nome=EXCLUDED.nome RETURNING id, nome",
        ("importante",),
    )[0]
    db.q("INSERT INTO decisao_tag VALUES (%s,%s) ON CONFLICT DO NOTHING", (1, tag["id"]), write=True)
    assert db.q("SELECT count(*) AS n FROM decisao_tag WHERE tag_id=%s", (tag["id"],), one=True)["n"] == 1

    db.q(
        "INSERT INTO anotacoes (decisao_id, texto, trecho) VALUES (%s,%s,%s) RETURNING id, texto",
        (1, "Leia com atenção", "trecho"),
    )
    assert db.q("SELECT texto FROM anotacoes WHERE decisao_id=%s", (1,), one=True)["texto"] == "Leia com atenção"

    db.q("INSERT INTO favoritos (decisao_id) VALUES (%s) ON CONFLICT DO NOTHING", (1,), write=True)
    assert db.q("SELECT count(*) AS n FROM favoritos WHERE decisao_id=%s", (1,), one=True)["n"] == 1

    db.q(
        "INSERT INTO buscas_salvas (nome, consulta, filtros) VALUES (%s,%s,%s) RETURNING id, nome",
        ("Dano moral", "dano moral", db.jsonb({"ramo": "civel"})),
    )
    salva = db.q("SELECT filtros FROM buscas_salvas WHERE nome=%s", ("Dano moral",), one=True)
    assert json.loads(salva["filtros"]) == {"ramo": "civel"}


def test_atualizacao_de_status_no_sqlite(local):
    db.q("UPDATE decisoes SET status=%s::status_vigencia WHERE id=%s", ("superada", 1), write=True)
    assert db.q("SELECT status FROM decisoes WHERE id=%s", (1,), one=True)["status"] == "superada"
