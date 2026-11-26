"""API de jurisprudência: busca, leitura e organização pessoal."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import db
from app.config import settings
from app.routers import busca, decisoes, organizacao

log = logging.getLogger(__name__)

MENSAGENS_STATUS = {
    400: "Requisição inválida.",
    401: "Autenticação necessária.",
    403: "Acesso negado.",
    404: "Recurso não encontrado.",
    405: "Método não permitido.",
    409: "Conflito com o estado atual do recurso.",
    422: "Dados inválidos. Confira os campos informados.",
    500: "Erro interno no servidor. Tente novamente mais tarde.",
}


def resposta_erro(
    status_code: int, detail: Any, mensagem: str | None = None
) -> JSONResponse:
    """Monta erro JSON mantendo `detail` e acrescentando mensagem em português."""
    corpo: dict[str, Any] = {"detail": detail}
    if mensagem:
        corpo["mensagem"] = mensagem
    return JSONResponse(status_code=status_code, content=jsonable_encoder(corpo))


def mensagem_validacao(tipo: str, ctx: dict[str, Any]) -> str:
    """Traduz os erros mais comuns do Pydantic para português."""
    if tipo == "value_error" and ctx.get("error"):
        return str(ctx["error"])
    traducoes = {
        "missing": "Campo obrigatório",
        "string_too_short": f"Texto muito curto (mínimo {ctx.get('min_length')} caracteres)",
        "string_too_long": f"Texto muito longo (máximo {ctx.get('max_length')} caracteres)",
        "too_short": f"Valor muito curto (mínimo {ctx.get('min_length')})",
        "too_long": f"Valor muito longo (máximo {ctx.get('max_length')})",
        "string_pattern_mismatch": "Formato inválido",
        "pattern_mismatch": "Formato inválido",
        "int_parsing": "Número inteiro inválido",
        "float_parsing": "Número inválido",
        "date_parsing": "Data inválida (use AAAA-MM-DD)",
        "datetime_parsing": "Data e hora inválidas",
        "greater_than_equal": f"Valor deve ser maior ou igual a {ctx.get('ge')}",
        "less_than_equal": f"Valor deve ser menor ou igual a {ctx.get('le')}",
        "literal_error": "Valor não permitido",
        "enum": "Valor não permitido",
        "model_type": "Corpo da requisição inválido",
    }
    return traducoes.get(tipo, "Valor inválido")


def _valor_seguro(valor: Any) -> Any:
    """Converte valores não serializáveis em texto para o JSON de erro."""
    if isinstance(valor, (str, int, float, bool, type(None), list, dict)):
        return valor
    return str(valor)


def traduzir_erros(erros: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Padroniza 422 mantendo a estrutura original de `detail`."""
    traduzidos: list[dict[str, Any]] = []
    for erro in erros:
        ctx = erro.get("ctx") or {}
        local = list(erro.get("loc", []))
        traduzidos.append(
            {
                "type": erro.get("type", ""),
                "loc": local,
                "msg": mensagem_validacao(str(erro.get("type", "")), ctx),
                "input": _valor_seguro(erro.get("input")),
                "campo": ".".join(str(parte) for parte in local[1:]) or "requisicao",
            }
        )
    return traduzidos


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Abre e fecha o pool de conexões junto com o ciclo de vida da app."""
    await db.abrir()
    try:
        yield
    finally:
        await db.fechar()


app = FastAPI(
    title="Jurisprudência",
    description="Busca, leitura e organização pessoal de decisões judiciais.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(StarletteHTTPException)
async def tratar_http_exception(request: Request, exc: StarletteHTTPException):
    return resposta_erro(
        exc.status_code,
        exc.detail,
        MENSAGENS_STATUS.get(exc.status_code, "Não foi possível concluir a solicitação."),
    )


@app.exception_handler(RequestValidationError)
async def tratar_validacao(request: Request, exc: RequestValidationError):
    return resposta_erro(
        422,
        traduzir_erros(exc.errors()),
        MENSAGENS_STATUS[422],
    )


@app.middleware("http")
async def tratar_erros(request: Request, call_next):
    """Captura falhas inesperadas e devolve JSON amigável."""
    try:
        return await call_next(request)
    except Exception:
        log.exception("Erro não tratado em %s", request.url.path)
        return resposta_erro(
            500,
            "Erro interno no servidor.",
            MENSAGENS_STATUS[500],
        )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(busca.router)
app.include_router(decisoes.router)
app.include_router(organizacao.router)


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}


# ---------------------------------------------------------------------
# Frontend estático (mesmo comportamento da versão anterior)
# ---------------------------------------------------------------------
FRONTEND = settings.frontend_dir


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND / "index.html")


if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
