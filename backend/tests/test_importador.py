"""Testes das funções puras e da CLI do importador."""
from __future__ import annotations

import hashlib
import json

import pytest

from importador import importar


def test_parse_data_iso():
    assert importar.parse_data("2024-03-15") == "2024-03-15"


def test_parse_data_brasileira():
    assert importar.parse_data("15/03/2024") == "2024-03-15"


def test_parse_data_compacta():
    assert importar.parse_data("20240315") == "2024-03-15"


def test_parse_data_invalida():
    assert importar.parse_data("31/02/2024") is None


@pytest.mark.parametrize("valor", ["", None, 0])
def test_parse_data_vazia(valor):
    assert importar.parse_data(valor) is None


def test_extrair_cnj_pontuado():
    numero = "0001234-56.2024.1.02.0001"
    assert importar.extrair_cnj(numero) == "0001234-56.2024.1.02.0001"


def test_extrair_cnj_sem_pontuacao():
    assert importar.extrair_cnj("00012345620241020001") == "0001234-56.2024.1.02.0001"


def test_extrair_cnj_invalido():
    assert importar.extrair_cnj("processo sem número") is None
    assert importar.extrair_cnj(None) is None


def test_limpar_remove_nulos_e_espacos():
    assert importar.limpar("  te\x00xto  ") == "texto"


def test_limpar_valor_vazio():
    assert importar.limpar("   ") is None
    assert importar.limpar(None) is None


def test_normalizar_preenche_campos_e_hash():
    bruto = {
        "fonte_id": "abc-1",
        "ementa": "Ementa",
        "tese": "Tese",
        "inteiro_teor": "Teor",
        "tipo": "ACORDAO",
        "numero_processo": "0001234-56.2024.1.02.0001",
        "data_julgamento": "15/03/2024",
    }
    registro = importar.normalizar(bruto, None)
    assert registro is not None
    assert registro["tipo"] == "acordao"
    assert registro["numero_cnj"] == "0001234-56.2024.1.02.0001"
    assert registro["data_julgamento"] == "2024-03-15"
    esperado = hashlib.sha256(b"Ementa\x1fTese\x1fTeor").hexdigest()
    assert registro["hash_conteudo"] == esperado
    assert list(registro) == importar.COLUNAS


def test_normalizar_tipo_desconhecido():
    registro = importar.normalizar(
        {"fonte_id": "x", "ementa": "E", "tipo": "tipo inventado"}, None
    )
    assert registro is not None
    assert registro["tipo"] == "outro"


def test_normalizar_respeita_mapa():
    registro = importar.normalizar(
        {"id": "x-9", "texto": "Ementa mapeada"},
        {"fonte_id": "id", "ementa": "texto"},
    )
    assert registro is not None
    assert registro["fonte_id"] == "x-9"
    assert registro["ementa"] == "Ementa mapeada"


def test_normalizar_sem_campos_obrigatorios():
    assert importar.normalizar({"ementa": "sem id"}, None) is None
    assert importar.normalizar({"fonte_id": "sem texto"}, None) is None
    assert importar.normalizar([], None) is None


def test_normalizar_legislacao_citada():
    registro = importar.normalizar(
        {"fonte_id": "x", "ementa": "E", "legislacao_citada": "Lei 1; Lei 2"}, None
    )
    assert registro is not None
    assert json.loads(registro["legislacao_citada"]) == ["Lei 1", "Lei 2"]

    registro_json = importar.normalizar(
        {"fonte_id": "y", "ementa": "E", "legislacao_citada": '["Lei 3"]'}, None
    )
    assert registro_json is not None
    assert json.loads(registro_json["legislacao_citada"]) == ["Lei 3"]


def test_ler_jsonl_ignora_linha_invalida(tmp_path, capsys):
    caminho = tmp_path / "decisoes.jsonl"
    caminho.write_text(
        '{"fonte_id": "1", "ementa": "Ementa 1"}\n'
        "linha quebrada\n"
        '{"fonte_id": "2", "ementa": "Ementa 2"}\n',
        encoding="utf-8",
    )
    registros = list(importar.ler_arquivo(caminho))
    assert len(registros) == 3
    assert registros[0]["fonte_id"] == "1"
    assert registros[1] == {}
    assert registros[2]["fonte_id"] == "2"
    assert "linha 2: JSON inválido" in capsys.readouterr().err


def test_ler_csv_com_bom(tmp_path):
    caminho = tmp_path / "decisoes.csv"
    caminho.write_text(
        "\ufefffonte_id,ementa,data_julgamento\nA,\"Ementa A\",15/03/2024\n",
        encoding="utf-8",
    )
    registros = list(importar.ler_arquivo(caminho))
    assert registros == [
        {"fonte_id": "A", "ementa": "Ementa A", "data_julgamento": "15/03/2024"}
    ]


def test_main_dry_run_nao_grava(tmp_path, monkeypatch, capsys):
    caminho = tmp_path / "decisoes.jsonl"
    caminho.write_text(
        '{"fonte_id": "1", "ementa": "Ementa 1"}\n'
        '{"fonte_id": "1", "ementa": "Ementa 1"}\n'
        "invalida\n"
        '{"fonte_id": "2", "ementa": "Ementa 2"}\n',
        encoding="utf-8",
    )

    def nao_conectar(*args, **kwargs):
        raise AssertionError("dry-run não deve abrir conexão")

    monkeypatch.setattr(importar.psycopg, "connect", nao_conectar)
    codigo = importar.main(
        [
            "--arquivo", str(caminho),
            "--tribunal", "STJ",
            "--fonte", "Teste",
            "--lote", "2",
            "--dry-run",
        ]
    )
    assert codigo == 0
    saida = capsys.readouterr().out
    assert "Dry-run: nenhuma alteração será gravada" in saida
    assert "Dry-run concluído: 2 válidos, 1 duplicados, 1 inválidos" in saida
    assert "Nada foi gravado" in saida


def test_main_arquivo_inexistente(tmp_path):
    with pytest.raises(SystemExit) as erro:
        importar.main(
            [
                "--arquivo", str(tmp_path / "nao-existe.jsonl"),
                "--tribunal", "STJ",
                "--fonte", "Teste",
            ]
        )
    assert "Arquivo não encontrado" in str(erro.value)


def test_main_lote_invalido(tmp_path):
    caminho = tmp_path / "vazio.jsonl"
    caminho.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit):
        importar.main(
            [
                "--arquivo", str(caminho),
                "--tribunal", "STJ",
                "--fonte", "Teste",
                "--lote", "0",
            ]
        )
