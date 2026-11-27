"""
Vercel Serverless Entrypoint for FastAPI
Handles Vercel path rewriting and ensures correct ASGI route matching.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.main import app as fastapi_app

async def app(scope, receive, send):
    """
    ASGI middleware ensuring that Vercel internal rewrites correctly map to FastAPI routes.
    """
    if scope["type"] == "http":
        headers = dict(scope.get("headers", []))
        # Vercel provides original client pathname in x-pathname or x-forwarded-uri
        raw_path = headers.get(b"x-pathname") or headers.get(b"x-forwarded-uri")
        if not raw_path:
            mp = headers.get(b"x-matched-path")
            if mp and mp != b"/api/index.py" and mp != b"/api":
                raw_path = mp
        
        if raw_path:
            clean_path = raw_path.decode("utf-8")
            if "?" in clean_path:
                clean_path = clean_path.split("?")[0]
            if clean_path and clean_path not in ["/api/index.py", "/api", "/api/"]:
                scope["path"] = clean_path
            elif scope.get("method") == "POST":
                scope["path"] = "/api/predict"
            else:
                scope["path"] = "/"
        elif scope.get("path") in ["/api/index.py", "/api", "/api/"]:
            if scope.get("method") == "POST":
                scope["path"] = "/api/predict"
            else:
                scope["path"] = "/"
            
    await fastapi_app(scope, receive, send)
