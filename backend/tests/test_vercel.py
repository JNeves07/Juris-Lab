"""Validações do entry point serverless e da configuração de deploy."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def test_entry_point_vercel_expoe_app_e_handler():
    if str(RAIZ) not in sys.path:
        sys.path.insert(0, str(RAIZ))
    modulo = importlib.import_module("api.index")
    assert hasattr(modulo, "app")
    assert hasattr(modulo, "handler")


def test_vercel_json_aponta_para_o_entry_point():
    config = json.loads((RAIZ / "vercel.json").read_text(encoding="utf-8"))
    assert config["builds"][0]["src"] == "api/index.py"
    assert config["routes"][0]["dest"] == "/api/index.py"


def test_requirements_incluem_dependencias_serverless():
    texto = (RAIZ / "backend" / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "pyjwt" in texto
    assert "mangum" in texto
