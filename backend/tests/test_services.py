"""Testes das funções puras de construção de consulta."""
from __future__ import annotations

from datetime import date

import pytest

from app import services


def test_consulta_sem_filtros():
    sql, params = services.construir_consulta_busca()
    assert "WITH pagina AS" in sql
    assert "FROM decisoes d JOIN tribunais t" in sql
    assert "ORDER BY rank DESC" not in sql
    assert "ORDER BY d.data_julgamento DESC NULLS LAST" in sql
    assert "LIMIT %(limit)s OFFSET %(offset)s" in sql
    assert params["cfg"] == "pt_unaccent"
    assert params["limit"] == 20
    assert params["offset"] == 0


def test_consulta_com_texto_usa_tsquery_e_headline():
    sql, params = services.construir_consulta_busca(texto="dano moral")
    assert "websearch_to_tsquery(%(cfg)s::regconfig, %(q)s)" in sql
    assert "ts_rank_cd(d.busca" in sql
    assert "ts_headline(%(cfg)s::regconfig" in sql
    assert "<mark>" in sql
    assert "ORDER BY rank DESC" in sql
    assert params["q"] == "dano moral"


def test_consulta_com_todos_filtros():
    filtros = {
        "texto": "dano moral",
        "tribunal": ["STJ", "TJCE"],
        "ramo": "civel",
        "tipo": "acordao",
        "status": "vigente",
        "relator": "Ministro Silva",
        "data_ini": date(2024, 1, 1),
        "data_fim": date(2024, 12, 31),
        "pasta_id": 7,
        "tag": "responsabilidade",
        "favoritos": True,
    }
    sql, params = services.construir_consulta_busca(**filtros)
    trechos = [
        "d.busca @@ websearch_to_tsquery",
        "t.sigla = ANY(%(tribunal)s)",
        "t.ramo = %(ramo)s",
        "d.tipo = %(tipo)s::tipo_decisao",
        "d.status = %(status)s::status_vigencia",
        "d.relator ILIKE %(relator)s",
        "d.data_julgamento >= %(data_ini)s",
        "d.data_julgamento <= %(data_fim)s",
        "dp.pasta_id = %(pasta_id)s",
        "g.nome = %(tag)s",
        "FROM favoritos f WHERE f.decisao_id = d.id",
    ]
    for trecho in trechos:
        assert trecho in sql
    assert params["tribunal"] == ["STJ", "TJCE"]
    assert params["tipo"] == "acordao"
    assert params["status"] == "vigente"
    assert params["relator"] == "%Ministro Silva%"


def test_ordem_data_asc():
    sql, _ = services.construir_consulta_busca(ordem="data_asc", texto="x")
    assert "ORDER BY d.data_julgamento ASC NULLS LAST" in sql
    assert "ORDER BY p.data_julgamento ASC NULLS LAST" in sql
    assert "ts_rank_cd" not in sql


def test_ordem_data_desc_padrao_quando_sem_texto():
    sql, _ = services.construir_consulta_busca(ordem="relevancia")
    assert "ORDER BY d.data_julgamento DESC NULLS LAST" in sql
    assert "ORDER BY p.data_julgamento DESC NULLS LAST" in sql


def test_paginacao():
    _, params = services.construir_consulta_busca(pagina=4, por_pagina=25)
    assert params["limit"] == 25
    assert params["offset"] == 75


def test_paginacao_invalida():
    with pytest.raises(ValueError, match="Paginação inválida"):
        services.construir_consulta_busca(pagina=0)


def test_contagem_limitada():
    sql, params = services.construir_contagem_busca(limite_contagem=50, texto="x")
    assert "SELECT count(*) AS n" in sql
    assert "LIMIT %(limite_contagem)s) s" in sql
    assert params["limite_contagem"] == 51
    assert params["q"] == "x"


def test_calcular_total_truncado():
    assert services.calcular_total(10_001) == (10_000, True)
    assert services.calcular_total(50) == (50, False)


def test_calcular_total_sem_truncar():
    assert services.calcular_total(None) == (0, False)
    assert services.calcular_total(99, limite_contagem=100) == (99, False)


def test_validar_periodo_invertido():
    with pytest.raises(ValueError, match="Data inicial"):
        services.validar_periodo("2024-05-01", "2024-04-01")
    services.validar_periodo("2024-04-01", "2024-05-01")


def test_validar_ordem_invalida():
    with pytest.raises(ValueError, match="Ordem inválida"):
        services.validar_ordem("aleatoria")


def test_validar_identificador_invalido():
    with pytest.raises(ValueError, match="Status inválido"):
        services.validar_identificador("STATUS INVÁLIDO!", "Status")
    assert services.validar_identificador("  sem_efeito ", "Status") == "sem_efeito"


def test_parametros_isolados_entre_builders():
    filtros = {"texto": "x"}
    sql_contagem, params_contagem = services.construir_contagem_busca(**filtros)
    sql_pagina, params_pagina = services.construir_consulta_busca(**filtros)
    params_pagina["offset"] = 999
    assert params_contagem["limite_contagem"] == 10_001
    assert "limite_contagem" not in params_pagina
    assert "offset" not in params_contagem
    assert sql_contagem != sql_pagina


def test_termo_para_like_remove_operadores():
    assert services.termo_para_like('"frase exata" -excluir OU alvo') == "frase exata alvo"


def test_normalizar_consulta_aceita_ou():
    assert services.normalizar_consulta("dano OU prejuízo") == "dano OR prejuízo"


def test_busca_com_ou_usa_or_no_tsquery():
    _, params = services.construir_consulta_busca(texto="dano ou prejuízo")
    assert params["q"] == "dano OR prejuízo"


def test_busca_texto_tambem_encontra_metadados():
    sql, params = services.construir_consulta_busca(texto="REsp 1000001/SP")
    assert "d.numero_processo ILIKE %(like_q)s" in sql
    assert "d.numero_cnj ILIKE %(like_q)s" in sql
    assert "d.relator ILIKE %(like_q)s" in sql
    assert params["like_q"] == "%REsp 1000001/SP%"


def test_busca_sem_fallback_like_quando_so_operadores():
    _, params = services.construir_consulta_busca(texto="-somente")
    assert "like_q" not in params


@pytest.mark.parametrize(
    ("campo", "valor", "mensagem"),
    [
        ("status", "foo", "Status inválido"),
        ("tipo", "foo", "Tipo inválido"),
        ("status", "qualquer", "Status inválido"),
        ("tipo", "acordao_inventado", "Tipo inválido"),
    ],
)
def test_enums_sintaticamente_validos_mas_desconhecidos(campo, valor, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        services.construir_filtros_busca(**{campo: valor})
    with pytest.raises(ValueError, match=mensagem):
        services.construir_consulta_busca(**{campo: valor})


def test_enums_validos_sao_normalizados():
    where, valores, _ = services.construir_filtros_busca(status="VIGENTE", tipo="ACORDAO")
    assert where
    assert valores["status"] == "vigente"
    assert valores["tipo"] == "acordao"


def test_consulta_de_exportacao_inclui_ementa_e_limite():
    sql, params = services.construir_consulta_busca(ordem="data_desc", pagina=1, por_pagina=25)
    assert "p.ementa" in sql
    assert params["limit"] == 25
