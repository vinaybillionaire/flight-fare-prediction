"""Vercel Serverless ASGI Entrypoint for FastAPI."""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.main import app as fastapi_app

_ENTRYPOINT_PATHS = {"/api/index.py", "/api/index"}


async def app(scope, receive, send):
    """Preserve real request paths on Vercel rewrites without clobbering FastAPI routes."""
    if scope["type"] == "http":
        current_path = scope.get("path", "/")
        if current_path in _ENTRYPOINT_PATHS:
            headers = dict(scope.get("headers", []))
            raw_path = scope.get("raw_path", b"").decode("utf-8", errors="ignore").split("?")[0]
            candidate = (
                headers.get(b"x-vercel-original-path")
                or headers.get(b"x-forwarded-uri")
                or headers.get(b"x-rewrite-url")
                or headers.get(b"x-matched-path")
            )
            if raw_path and raw_path not in _ENTRYPOINT_PATHS:
                scope["path"] = raw_path
            elif candidate:
                decoded = candidate.decode("utf-8", errors="ignore").split("?")[0]
                if decoded and decoded not in _ENTRYPOINT_PATHS:
                    scope["path"] = decoded
                else:
                    scope["path"] = "/api/predict" if scope.get("method") == "POST" else "/"
            else:
                scope["path"] = "/api/predict" if scope.get("method") == "POST" else "/"

    await fastapi_app(scope, receive, send)
