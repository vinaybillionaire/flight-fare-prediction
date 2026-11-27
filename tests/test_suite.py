"""
Unit & Integration Tests for ML Model and FastAPI Endpoints
Step 14 in the 16-step flow.
"""

import os
import sys
import pytest
import json
import joblib
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_model_files_exist():
    """Verify saved model and feature list exist (Step 10 check)."""
    model_path = os.path.join(PROJECT_ROOT, "models", "flight_rf_model.pkl")
    features_path = os.path.join(PROJECT_ROOT, "models", "feature_names.json")
    metrics_path = os.path.join(PROJECT_ROOT, "models", "model_metrics.json")
    assert os.path.exists(model_path), "Model file missing"
    assert os.path.exists(features_path), "Feature names missing"
    assert os.path.exists(metrics_path), "Metrics file missing"

def test_model_inference():
    """Verify model can perform prediction on dummy vector."""
    model_path = os.path.join(PROJECT_ROOT, "models", "flight_rf_model.pkl")
    features_path = os.path.join(PROJECT_ROOT, "models", "feature_names.json")
    model = joblib.load(model_path)
    with open(features_path, "r") as f:
        features = json.load(f)
    import pandas as pd
    dummy_input = [0] * len(features)
    # Set stops=0, duration=170
    dummy_input[0] = 0
    dummy_input[8] = 170
    dummy_df = pd.DataFrame([dummy_input], columns=features)
    prediction = model.predict(dummy_df)
    assert len(prediction) == 1
    assert prediction[0] > 0, "Predicted price must be positive"

def test_health_endpoint():
    """Verify health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["model_loaded"] is True

def test_api_predict():
    """Verify POST /api/predict returns valid fare and logs to DB."""
    payload = {
        "airline": "IndiGo",
        "source": "Banglore",
        "destination": "Delhi",
        "journey_date": "2026-12-04",
        "dep_time": "10:00",
        "arrival_time": "12:50",
        "total_stops": 0
    }
    response = client.post("/api/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["predicted_fare"] > 2000
    assert "prediction_id" in data
    assert data["fare_category"] in ["Budget", "Standard", "Premium", "Surge"]

def test_api_history():
    """Verify GET /api/history returns logged records."""
    response = client.get("/api/history")
    assert response.status_code == 200
    data = response.json()
    assert "history" in data
    assert isinstance(data["history"], list)
    assert len(data["history"]) >= 1

def test_identical_origin_destination_rejected():
    """Verify selecting same origin and destination returns 400 Bad Request."""
    payload = {
        "airline": "IndiGo",
        "source": "Delhi",
        "destination": "Delhi",
        "journey_date": "2026-12-04",
        "dep_time": "10:00",
        "arrival_time": "12:50",
        "total_stops": 0
    }
    response = client.post("/api/predict", json=payload)
    assert response.status_code == 400
    assert "identical" in response.json()["detail"].lower()

def test_multistop_transit_route_and_duration():
    """Verify 2-stop flight returns intermediate transit hubs and realistic duration."""
    payload = {
        "airline": "Jet Airways",
        "source": "Banglore",
        "destination": "Hyderabad",
        "journey_date": "2026-12-04",
        "dep_time": "08:30",
        "arrival_time": "08:32", # Even if bad arrival time passed, guardrail enforces realistic time
        "total_stops": 2
    }
    response = client.post("/api/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    details = data["flight_details"]
    assert len(details["transit_hubs"]) == 2
    assert "Chennai (MAA)" in details["transit_hubs"][0]
    assert "Tirupati (TIR)" in details["transit_hubs"][1]
    assert "8h" in details["duration"] or "7h" in details["duration"]

def test_fare_decomposition_math_balance():
    """Verify Explainable AI decomposition components sum up exactly to predicted fare."""
    payload = {
        "airline": "Vistara",
        "source": "Delhi",
        "destination": "Cochin",
        "journey_date": "2026-12-05",
        "dep_time": "08:30",
        "arrival_time": "11:45",
        "total_stops": 1
    }
    response = client.post("/api/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    predicted = data["predicted_fare"]
    decomp = data["fare_decomposition"]
    
    total_decomp = 0.0
    for item in decomp:
        clean_amt = item["amount"].replace("Rs.", "").replace("₹", "").replace("+", "").replace(",", "").strip()
        total_decomp += float(clean_amt)
    
    assert abs(total_decomp - predicted) < 0.1, f"Decomposition sum {total_decomp} must equal predicted fare {predicted}"

def test_three_stops_returns_three_hubs():
    """Verify selecting 3 stops returns exactly 3 distinct intermediate transit hubs."""
    payload = {
        "airline": "Air India",
        "source": "Delhi",
        "destination": "Cochin",
        "journey_date": "2026-12-05",
        "dep_time": "08:30",
        "arrival_time": "20:45",
        "total_stops": 3
    }
    response = client.post("/api/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    hubs = data["flight_details"]["transit_hubs"]
    assert len(hubs) == 3, f"Expected 3 hubs, got {len(hubs)}: {hubs}"
    assert len(set(hubs)) == 3, f"All 3 hubs must be distinct: {hubs}"

def test_invalid_date_format_returns_400():
    """Verify malformed date returns 400 Bad Request instead of 500 error."""
    payload = {
        "airline": "IndiGo",
        "source": "Banglore",
        "destination": "Delhi",
        "journey_date": "not-a-valid-date",
        "dep_time": "10:00",
        "arrival_time": "12:50",
        "total_stops": 0
    }
    response = client.post("/api/predict", json=payload)
    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower()

if __name__ == "__main__":
    print("Running tests...")
    test_model_files_exist()
    print("  [PASS] Model files exist")
    test_model_inference()
    print("  [PASS] Model inference successful")
    test_health_endpoint()
    print("  [PASS] Health check passed")
    test_api_predict()
    print("  [PASS] Predict endpoint verified")
    test_api_history()
    print("  [PASS] Database history verified")
    print("\nALL STEP 14 VERIFICATION TESTS PASSED SUCCESSFULLY!")
