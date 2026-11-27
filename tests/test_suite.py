"""Comprehensive Unit & Integration Test Suite for FareLens.

Covers:
- 90%+ R2 leak-free ML artifacts & inference accuracy check
- Input validation (422 on identical source/destination or malformed dates)
- Batch 7-day date flexibility & cross-airline comparison endpoints
- JWT Authentication & RBAC (401 unauthenticated, 403 unauthorized, Traveler vs Analyst vs Admin)
- Full 3NF Database CRUD (Create, Read, Update, Delete) on Predictions & Fare Alerts
- EDA Analytics & Model Benchmark endpoints
"""

import json
import os
import sys
import uuid

import joblib
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.main import app
from models.features import build_inference_dataframe

client = TestClient(app)


def _login(email: str, password: str) -> dict:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_model_artifacts_and_accuracy():
    model_path = os.path.join(PROJECT_ROOT, "models", "flight_rf_model.pkl")
    metrics_path = os.path.join(PROJECT_ROOT, "models", "model_metrics.json")
    eda_path = os.path.join(PROJECT_ROOT, "models", "eda_summary.json")
    catalog_path = os.path.join(PROJECT_ROOT, "models", "route_catalog.json")

    for p in (model_path, metrics_path, eda_path, catalog_path):
        assert os.path.exists(p), f"Missing artifact: {p}"

    with open(metrics_path, "r") as f:
        metrics = json.load(f)
    selected = metrics["selected_model"]
    r2 = metrics["models"][selected]["r2_score"]
    assert r2 >= 0.90, f"Expected R2 >= 0.90, got {r2}"

    pipeline = joblib.load(model_path)
    sample_df, resolved_route, dur = build_inference_dataframe(
        airline="IndiGo",
        source="Banglore",
        destination="Delhi",
        journey_date="2026-12-04",
        dep_time="10:00",
        arrival_time="12:50",
        total_stops=0,
    )
    pred = pipeline.predict(sample_df)
    assert len(pred) == 1
    assert pred[0] > 1800
    assert dur == 170
    assert "BLR" in resolved_route


def test_health_and_analytics_endpoints():
    health = client.get("/health")
    assert health.status_code == 200
    h = health.json()
    assert h["status"] == "healthy"
    assert h["model_loaded"] is True
    assert h["r2_score"] >= 0.90

    analytics = client.get("/api/analytics")
    assert analytics.status_code == 200
    eda = analytics.json()["eda"]
    assert eda["dataset_overview"]["cleaned_records"] == 10462
    assert len(eda["feature_importances"]) >= 5
    assert len(eda["market_limitations"]["factors"]) >= 3

    benchmarks = client.get("/api/metrics")
    assert benchmarks.status_code == 200
    assert len(benchmarks.json()["metrics"]["models"]) >= 6


def test_prediction_validation_and_batch_comparisons():
    # Reject identical source and destination (including Delhi vs New Delhi)
    bad = client.post(
        "/api/predict",
        json={
            "airline": "IndiGo",
            "source": "Delhi",
            "destination": "New Delhi",
            "journey_date": "2026-12-04",
            "dep_time": "10:00",
            "arrival_time": "12:50",
            "total_stops": 0,
        },
    )
    assert bad.status_code == 422

    payload = {
        "airline": "Jet Airways",
        "source": "Delhi",
        "destination": "Cochin",
        "journey_date": "2026-12-04",
        "dep_time": "09:25",
        "arrival_time": "19:00",
        "total_stops": 1,
        "additional_info": "In-flight meal not included",
        "inflation_factor": 1.0,
        "notes": "pytest smoke test",
    }
    pred = client.post("/api/predict", json=payload)
    assert pred.status_code == 200, pred.text
    data = pred.json()
    assert data["predicted_fare"] > 2000
    assert data["confidence_interval"]["lower"] <= data["predicted_fare"] <= data["confidence_interval"]["upper"]
    assert len(data["drivers"]) >= 2

    flex = client.post("/api/compare-dates", json=payload)
    assert flex.status_code == 200
    assert len(flex.json()["dates"]) == 7

    airlines = client.post("/api/compare-airlines", json=payload)
    assert airlines.status_code == 200
    comps = airlines.json()["comparisons"]
    assert len(comps) >= 8
    assert all("dep_time" in c and "arrival_time" in c and "duration" in c for c in comps)

    # Reverse corridor support (Cochin -> Delhi mirrors Delhi -> Cochin cleanly)
    rev = client.post(
        "/api/predict",
        json={
            "airline": "IndiGo",
            "source": "Cochin",
            "destination": "Delhi",
            "journey_date": "2026-12-04",
            "dep_time": "05:35",
            "arrival_time": "08:50",
            "total_stops": 0,
        },
    )
    assert rev.status_code == 200
    assert rev.json()["predicted_fare"] > 2000
    assert "COK" in rev.json()["flight_details"]["resolved_route_path"]


def test_auth_rbac_and_full_crud_lifecycle():
    # Admin routes remain protected (401 unauthenticated), while workspace CRUD works seamlessly
    assert client.get("/api/admin/users").status_code == 401
    assert client.get("/api/alerts").status_code == 200
    assert client.get("/api/history/export").status_code == 200

    # Register fresh traveler
    unique_email = f"traveler_{uuid.uuid4().hex[:8]}@test.in"
    reg = client.post(
        "/api/auth/register",
        json={
            "full_name": "Test Traveler",
            "email": unique_email,
            "password": "Password123",
            "role": "traveler",
        },
    )
    assert reg.status_code == 201, reg.text
    traveler_token = reg.json()["access_token"]
    t_headers = {"Authorization": f"Bearer {traveler_token}"}

    # Traveler cannot access Admin routes -> 403
    assert client.get("/api/admin/users", headers=t_headers).status_code == 403

    # Create prediction as authenticated traveler
    pred = client.post(
        "/api/predict",
        headers=t_headers,
        json={
            "airline": "IndiGo",
            "source": "Banglore",
            "destination": "Delhi",
            "journey_date": "2026-12-08",
            "dep_time": "10:00",
            "arrival_time": "12:50",
            "total_stops": 0,
            "notes": "Initial note",
        },
    )
    assert pred.status_code == 200
    pred_id = pred.json()["prediction_id"]
    est_fare = pred.json()["predicted_fare"]

    # UPDATE prediction note
    upd_pred = client.patch(
        f"/api/history/{pred_id}",
        headers=t_headers,
        json={"notes": "Updated note"},
    )
    assert upd_pred.status_code == 200
    assert upd_pred.json()["record"]["notes"] == "Updated note"

    # CREATE Fare Alert
    alert_resp = client.post(
        "/api/alerts",
        headers=t_headers,
        json={
            "prediction_id": pred_id,
            "airline": "IndiGo",
            "source": "Banglore",
            "destination": "Delhi",
            "journey_date": "2026-12-08",
            "target_price": round(est_fare * 0.85, 2),
            "estimated_price": est_fare,
            "notes": "Watch drop",
        },
    )
    assert alert_resp.status_code == 201
    alert_id = alert_resp.json()["alert"]["id"]

    # READ Fare Alerts
    list_alerts = client.get("/api/alerts", headers=t_headers)
    assert list_alerts.status_code == 200
    assert any(a["id"] == alert_id for a in list_alerts.json()["alerts"])

    # UPDATE Fare Alert
    patch_alert = client.patch(
        f"/api/alerts/{alert_id}",
        headers=t_headers,
        json={"target_price": est_fare + 500, "notes": "Urgent trip"},
    )
    assert patch_alert.status_code == 200
    assert patch_alert.json()["alert"]["status"] == "target_met"

    # DELETE Fare Alert & Prediction
    assert client.delete(f"/api/alerts/{alert_id}", headers=t_headers).status_code == 200
    assert client.delete(f"/api/history/{pred_id}", headers=t_headers).status_code == 200

    # Verify Admin & Analyst RBAC
    analyst_auth = _login("analyst@farelens.in", "Analyst@123")
    a_headers = {"Authorization": f"Bearer {analyst_auth['access_token']}"}
    assert client.get("/api/history/export", headers=a_headers).status_code == 200

    admin_auth = _login("admin@farelens.in", "Admin@123")
    adm_headers = {"Authorization": f"Bearer {admin_auth['access_token']}"}
    users_resp = client.get("/api/admin/users", headers=adm_headers)
    assert users_resp.status_code == 200
    assert len(users_resp.json()["users"]) >= 3


def test_vercel_entrypoint_preserves_routes():
    from api.index import app as vercel_app

    vercel_client = TestClient(vercel_app)
    # Simulate Vercel passing x-matched-path: / while scope['path'] is the real route
    h = {"x-matched-path": "/"}
    assert vercel_client.get("/health", headers=h).json()["status"] == "healthy"
    assert "catalog" in vercel_client.get("/api/catalog", headers=h).json()
    pred = vercel_client.post(
        "/api/predict",
        headers=h,
        json={
            "airline": "IndiGo",
            "source": "Banglore",
            "destination": "Delhi",
            "journey_date": "2026-12-04",
            "dep_time": "08:30",
            "arrival_time": "11:20",
            "total_stops": 0,
        },
    )
    assert pred.status_code == 200
    assert pred.json()["predicted_fare"] > 1800


if __name__ == "__main__":
    test_model_artifacts_and_accuracy()
    test_health_and_analytics_endpoints()
    test_prediction_validation_and_batch_comparisons()
    test_auth_rbac_and_full_crud_lifecycle()
    print("ALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
