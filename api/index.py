"""Vercel Serverless ASGI Entrypoint for FastAPI."""

import os
import sys
from urllib.parse import parse_qsl, urlencode

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.main import app as fastapi_app

_ENTRYPOINT_PATHS = {"/api/index.py", "/api/index"}


async def app(scope, receive, send):
    """Restore original request path & query string from Vercel rewrites cleanly."""
    if scope["type"] == "http":
        raw_qs = scope.get("query_string", b"").decode("utf-8", errors="ignore")
        params = parse_qsl(raw_qs, keep_blank_values=True)
        vpath = None
        remaining_params = []
        for k, v in params:
            if k == "__vpath" and vpath is None:
                vpath = v
            else:
                remaining_params.append((k, v))

        if vpath is not None:
            norm_path = "/" + vpath.lstrip("/")
            if norm_path in _ENTRYPOINT_PATHS:
                norm_path = "/api/predict" if scope.get("method") == "POST" else "/"
            scope["path"] = norm_path
            scope["raw_path"] = norm_path.encode("utf-8")
            scope["query_string"] = urlencode(remaining_params).encode("utf-8")
        else:
            current_path = scope.get("path", "/")
            if current_path in _ENTRYPOINT_PATHS:
                headers = dict(scope.get("headers", []))
                raw_path = scope.get("raw_path", b"").decode("utf-8", errors="ignore").split("?")[0]
                candidate = (
                    headers.get(b"x-vercel-original-path")
                    or headers.get(b"x-forwarded-uri")
                    or headers.get(b"x-rewrite-url")
                )
                if raw_path and raw_path not in _ENTRYPOINT_PATHS:
                    scope["path"] = raw_path
                elif candidate:
                    decoded = candidate.decode("utf-8", errors="ignore").split("?")[0]
                    scope["path"] = decoded if decoded and decoded not in _ENTRYPOINT_PATHS else "/"
                else:
                    scope["path"] = "/api/predict" if scope.get("method") == "POST" else "/"

    await fastapi_app(scope, receive, send)
