"""Single-Command Application Launcher (Steps 15 & 16: Deployment & URL Generation).

Usage:
    python3 run.py
Serves FareLens at http://127.0.0.1:8000 and Swagger Docs at http://127.0.0.1:8000/docs
"""

import os
import sys
import uvicorn

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "127.0.0.1")
    print("=" * 70)
    print("  FareLens | Airfare Price Estimation & Fare Pattern Analysis-II")
    print("  Team: G1716 | Mentor: Padma Priya T")
    print(f"  Live Web App : http://{host}:{port}")
    print(f"  Swagger Docs : http://{host}:{port}/docs")
    print("=" * 70)
    uvicorn.run("backend.main:app", host=host, port=port, reload=False)
