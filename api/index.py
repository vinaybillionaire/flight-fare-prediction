"""Vercel Serverless ASGI Entrypoint for FastAPI."""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.main import app as fastapi_app


async def app(scope, receive, send):
    if scope["type"] == "http":
        headers = dict(scope.get("headers", []))
        matched_path = headers.get(b"x-matched-path")
        if matched_path and matched_path not in (b"/api/index.py", b"/api"):
            clean_path = matched_path.decode("utf-8").split("?")[0]
            scope["path"] = clean_path
        elif scope["path"] in ["/api/index.py", "/api", "/api/"]:
            scope["path"] = "/api/predict" if scope.get("method") == "POST" else "/"
    await fastapi_app(scope, receive, send)
