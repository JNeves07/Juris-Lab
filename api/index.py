"""Entry point da Vercel (serverless).

O backend fica em ``backend/``; ajustamos o ``sys.path`` para que ``app`` e
``importador`` sejam importáveis no runtime @vercel/python. O runtime reconhece
a variável ASGI ``app``; ``handler`` (Mangum) mantém compatibilidade Lambda.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from mangum import Mangum  # noqa: E402

from app.main import app  # noqa: E402

handler = Mangum(app, lifespan="off")

__all__ = ["app", "handler"]
