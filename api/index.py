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
        # Vercel sends the client-requested URL in x-matched-path
        matched_path = headers.get(b"x-matched-path")
        if matched_path:
            clean_path = matched_path.decode("utf-8")
            # Strip query params if present in matched path
            if "?" in clean_path:
                clean_path = clean_path.split("?")[0]
            scope["path"] = clean_path
        elif scope["path"] in ["/api/index.py", "/api", "/api/"]:
            scope["path"] = "/"
            
    await fastapi_app(scope, receive, send)
