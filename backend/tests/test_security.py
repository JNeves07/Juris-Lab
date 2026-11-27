"""Testes offline de expiração, assinatura, audiência e segredos do JWT."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException

from app import config, security


def cfg_segura():
    """Configuração com segredos próprios, sem depender do ambiente do teste."""
    return replace(
        config.settings,
        jwt_secret="chave-de-teste-com-mais-de-trinta-caracteres",
        admin_password="senha-de-teste-forte",
        permitir_segredos_padrao=False,
    )


def test_token_tem_sub_aud_e_eh_valido():
    cfg = cfg_segura()
    token = security.criar_token("admin", cfg=cfg)
    bruto = jwt.decode(
        token, cfg.jwt_secret, algorithms=["HS256"], options={"verify_aud": False}
    )
    assert bruto["sub"] == "admin"
    assert bruto["aud"] == "juris-lab"
    assert bruto["iss"] == "jurislab"
    assert security.validar_token(token, cfg)["sub"] == "admin"


def test_token_expirado():
    cfg = cfg_segura()
    token = security.criar_token(minutos=-1, cfg=cfg)
    with pytest.raises(HTTPException) as erro:
        security.validar_token(token, cfg)
    assert erro.value.status_code == 401


def test_token_adulterado():
    cfg = cfg_segura()
    token = security.criar_token(cfg=cfg)
    adulterado = token[:10] + ("a" if token[10] != "a" else "b") + token[11:]
    with pytest.raises(HTTPException) as erro:
        security.validar_token(adulterado, cfg)
    assert erro.value.status_code == 401


def test_audiencia_incorreta():
    cfg = cfg_segura()
    agora = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "admin", "iat": agora,
            "exp": agora + timedelta(minutes=5),
            "iss": security.EMISSOR, "aud": "outro-sistema",
        },
        cfg.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as erro:
        security.validar_token(token, cfg)
    assert erro.value.status_code == 401


def test_sem_sub_e_com_sub_invalido():
    cfg = cfg_segura()
    agora = datetime.now(UTC)
    base = {
        "iat": agora, "exp": agora + timedelta(minutes=5),
        "iss": security.EMISSOR, "aud": security.AUDIENCIA,
    }
    for dados in (base, {**base, "sub": "<script>"}):
        token = jwt.encode(dados, cfg.jwt_secret, algorithm="HS256")
        with pytest.raises(HTTPException) as erro:
            security.validar_token(token, cfg)
        assert erro.value.status_code == 401

    with pytest.raises(ValueError, match="Sujeito"):
        security.criar_token("admin<script>", cfg=cfg)


def test_segredos_padrao_sao_recusados_sem_autorizacao():
    cfg = replace(
        cfg_segura(),
        jwt_secret="dev-only-jurislab-change-me-in-production",
        admin_password="admin",
    )
    with pytest.raises(RuntimeError, match="autorização explícita"):
        security.criar_token(cfg=cfg)
    with pytest.raises(HTTPException) as erro:
        security.validar_token("token-qualquer", cfg)
    assert erro.value.status_code == 401

    permitido = replace(cfg, permitir_segredos_padrao=True)
    token = security.criar_token(cfg=permitido)
    assert security.validar_token(token, permitido)["aud"] == security.AUDIENCIA
