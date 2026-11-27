"""Testes da configuração centralizada e do LOG_LEVEL."""
from __future__ import annotations

import logging
from pathlib import Path

from app import config


def test_modo_padrao_e_precedencia(monkeypatch):
    monkeypatch.delenv("JLS_MODE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert config.Settings.from_env().modo == "sqlite"

    monkeypatch.setenv("DATABASE_URL", "postgresql://exemplo/db")
    assert config.Settings.from_env().modo == "postgres"

    monkeypatch.setenv("JLS_MODE", "sqlite")
    assert config.Settings.from_env().modo == "sqlite"


def test_banco_em_memoria_na_vercel(monkeypatch):
    monkeypatch.delenv("JLS_DB_PATH", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    assert config.Settings.from_env().db_path == ":memory:"

    monkeypatch.setenv("JLS_DB_PATH", "personalizado.sqlite3")
    assert config.Settings.from_env().db_path == Path("personalizado.sqlite3")


def test_limites_e_export_max(monkeypatch):
    monkeypatch.setenv("LIMITE_CONTAGEM", "abc")
    monkeypatch.delenv("JLS_EXPORT_MAX", raising=False)
    cfg = config.Settings.from_env()
    assert cfg.limite_contagem == 10_000
    assert cfg.export_max == 1_000

    monkeypatch.setenv("JLS_EXPORT_MAX", "0")
    assert config.Settings.from_env().export_max == 1


def test_segredos_padrao_e_autorizacao_explicita(monkeypatch):
    monkeypatch.delenv("JLS_JWT_SECRET", raising=False)
    monkeypatch.delenv("JLS_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("JLS_ALLOW_DEFAULT_SECRETS", raising=False)
    cfg = config.Settings.from_env()
    assert cfg.secrets_padrao is True
    assert cfg.segredos_utilizaveis is False

    monkeypatch.setenv("JLS_ALLOW_DEFAULT_SECRETS", "1")
    assert config.Settings.from_env().segredos_utilizaveis is True

    monkeypatch.setenv("JLS_JWT_SECRET", "chave-longa-aleatoria")
    monkeypatch.setenv("JLS_ADMIN_PASSWORD", "senha-forte")
    cfg = config.Settings.from_env()
    assert cfg.secrets_padrao is False
    assert cfg.segredos_utilizaveis is True


def test_log_level_aplicado_e_invalido_cai_em_info(monkeypatch):
    raiz = logging.getLogger()
    nivel_original = raiz.level
    try:
        monkeypatch.setenv("LOG_LEVEL", "warning")
        config.configurar_logging(config.Settings.from_env())
        assert raiz.level == logging.WARNING

        monkeypatch.setenv("LOG_LEVEL", "inexistente")
        config.configurar_logging(config.Settings.from_env())
        assert raiz.level == logging.INFO
    finally:
        raiz.setLevel(nivel_original)
