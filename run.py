"""
Single-Command Application Launcher (Steps 15 & 16: Deployment & URL Generation)
Usage: python run.py
Serves the web application at http://127.0.0.1:8000
"""

import os
import sys
import uvicorn

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

if __name__ == "__main__":
    print("=" * 65)
    print("  AeroPrice AI: Flight Fare Estimation & Fare Pattern Analysis-II")
    print("  Team: G1716 (Cheekati Vinay & Team) | Mentor: Padma Priya T")
    print("  Host: http://127.0.0.1:8000")
    print("  API Docs: http://127.0.0.1:8000/docs")
    print("=" * 65)
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)
