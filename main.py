"""Root ASGI re-export so `uvicorn main:app` and `python run.py` both work cleanly."""

from backend.main import app  # noqa: F401
