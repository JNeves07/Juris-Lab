"""API de jurisprudência: fábrica FastAPI, segurança e registro dos roteadores."""
from __future__ import annotations

import logging
import re
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import config, db
from app.config import Settings
from app.routers import admin, busca, decisoes, organizacao, status

log = logging.getLogger(__name__)
_hits: dict[str, deque[float]] = defaultdict(deque)
LIMITE_IPS = 2_048
IP_RE = re.compile(r"^[A-Za-z0-9:._-]{1,64}$")

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


def ip_cliente(request: Request, cfg: Settings | None = None) -> str:
    """Usa o IP direto da conexão, salvo opt-in explícito para proxy confiável."""
    configuracao = cfg or config.settings
    if configuracao.trust_proxy:
        encaminhado = request.headers.get("x-forwarded-for", "")[:128]
        candidato = encaminhado.split(",")[0].strip()
        if IP_RE.fullmatch(candidato):
            return candidato
    return request.client.host if request.client else "?"


def _limpar_hits(agora: float, cfg: Settings) -> None:
    """Descarta janelas vencidas e limita a quantidade de IPs rastreados."""
    corte = agora - max(cfg.rate_window, 1)
    for ip in [chave for chave, janela in _hits.items() if not janela or janela[-1] < corte]:
        del _hits[ip]
    while len(_hits) > LIMITE_IPS:
        mais_antigo = min(_hits, key=lambda chave: _hits[chave][-1] if _hits[chave] else 0)
        del _hits[mais_antigo]


def registrar_tentativa(ip: str, cfg: Settings | None = None) -> bool:
    """Registra uma tentativa de token; False indica janela excedida."""
    configuracao = cfg or config.settings
    agora = time.monotonic()
    janela = _hits[ip]
    while janela and janela[0] < agora - configuracao.rate_window:
        janela.popleft()
    if len(janela) >= configuracao.rate_limit:
        _limpar_hits(agora, configuracao)
        return False
    janela.append(agora)
    _limpar_hits(agora, configuracao)
    return True


def definir_request_id(request: Request, cfg: Settings | None = None) -> str | None:
    """Reusa um UUID válido do cliente ou gera um novo, quando habilitado."""
    configuracao = cfg or config.settings
    if not configuracao.request_id:
        return None
    informado = request.headers.get("x-request-id", "")[:64].strip()
    try:
        return str(uuid.UUID(informado)) if informado else str(uuid.uuid4())
    except ValueError:
        return str(uuid.uuid4())


def aplicar_cabecalhos(request: Request, resposta, identificador: str | None = None):
    """Cabeçalhos de segurança aplicados até mesmo nas respostas de limite."""
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["X-Frame-Options"] = "DENY"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    resposta.headers["Cache-Control"] = (
        "no-store" if request.url.path.startswith("/api/") else "public, max-age=300"
    )
    resposta.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; script-src 'self'; connect-src 'self'"
    )
    if identificador:
        resposta.headers["X-Request-ID"] = identificador
        request.state.request_id = identificador
    return resposta


def criar_app() -> FastAPI:
    """Cria a aplicação; usada por uvicorn, testes e pelo handler da Vercel."""
    config.configurar_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Abre e fecha o backend junto com o ciclo de vida da app."""
        await db.abrir()
        try:
            yield
        finally:
            await db.fechar()

    aplicacao = FastAPI(
        title="Juris-Lab",
        description=(
            "Busca, leitura e organização pessoal de decisões judiciais. "
            "Funciona sem configuração com SQLite local ou com PostgreSQL/pgvector."
        ),
        version=config.settings.versao,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    @aplicacao.exception_handler(StarletteHTTPException)
    async def tratar_http_exception(request: Request, exc: StarletteHTTPException):
        return resposta_erro(
            exc.status_code,
            exc.detail,
            MENSAGENS_STATUS.get(exc.status_code, "Não foi possível concluir a solicitação."),
        )

    @aplicacao.exception_handler(RequestValidationError)
    async def tratar_validacao(request: Request, exc: RequestValidationError):
        return resposta_erro(422, traduzir_erros(exc.errors()), MENSAGENS_STATUS[422])

    @aplicacao.middleware("http")
    async def seguranca_e_limites(request: Request, call_next):
        configuracao = config.settings
        identificador = definir_request_id(request, configuracao)
        if request.url.path == "/api/admin/token" and request.method == "POST":
            if not registrar_tentativa(ip_cliente(request, configuracao), configuracao):
                return aplicar_cabecalhos(
                    request,
                    resposta_erro(
                        429,
                        "Muitas tentativas. Aguarde um minuto.",
                        "Limite de requisições excedido.",
                    ),
                    identificador,
                )

        try:
            resposta = await call_next(request)
        except Exception:
            log.exception("Erro não tratado em %s", request.url.path)
            resposta = resposta_erro(500, "Erro interno no servidor.", MENSAGENS_STATUS[500])
        return aplicar_cabecalhos(request, resposta, identificador)

    if config.settings.cors_origins:
        aplicacao.add_middleware(
            CORSMiddleware,
            allow_origins=list(config.settings.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    aplicacao.include_router(status.router)
    aplicacao.include_router(busca.router)
    aplicacao.include_router(decisoes.router)
    aplicacao.include_router(organizacao.router)
    aplicacao.include_router(admin.router)

    frontend = config.settings.frontend_dir

    @aplicacao.get("/", include_in_schema=False)
    def index():
        return FileResponse(frontend / "index.html")

    @aplicacao.get("/favicon.svg", include_in_schema=False)
    def favicon():
        return FileResponse(frontend / "assets" / "favicon.svg")

    if frontend.exists():
        aplicacao.mount("/static", StaticFiles(directory=frontend), name="static")

    return aplicacao


app = criar_app()
