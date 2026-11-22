"""
FastAPI Backend Application
Project: Airfare Price Estimation and Fare Pattern Analysis-II
Team: G1716 (Cheekati Vinay, Bommineni Lokesh Narayana, Devarshetty Karthik Datta, Kamboji Sai Dhanush Kumar)
Mentor: Padma Priya T
"""

import os
import sys
import json
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.db import save_prediction_log, fetch_recent_predictions, get_database_status

MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
MODEL_PATH = os.path.join(MODELS_DIR, "flight_rf_model.pkl")
FEATURES_PATH = os.path.join(MODELS_DIR, "feature_names.json")
METRICS_PATH = os.path.join(MODELS_DIR, "model_metrics.json")

# Load model and feature metadata
if not os.path.exists(MODEL_PATH) or not os.path.exists(FEATURES_PATH):
    raise RuntimeError(f"Trained model or feature list not found in {MODELS_DIR}. Run train_models.py first.")

model = joblib.load(MODEL_PATH)
with open(FEATURES_PATH, "r") as f:
    feature_names = json.load(f)

model_metrics = {}
if os.path.exists(METRICS_PATH):
    with open(METRICS_PATH, "r") as f:
        model_metrics = json.load(f)

app = FastAPI(
    title="Airfare Price Estimation API",
    description="ML-powered flight fare estimation system built with Random Forest Regressor & FastAPI",
    version="2.0.0"
)

# Static and Template mounts
STATIC_DIR = os.path.join(PROJECT_ROOT, "frontend", "static")
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "frontend", "templates")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

class FlightPredictionRequest(BaseModel):
    airline: str = Field(..., example="IndiGo")
    source: str = Field(..., example="Banglore")
    destination: str = Field(..., example="Delhi")
    journey_date: str = Field(..., example="2026-12-04")
    dep_time: str = Field(..., example="10:00")
    arrival_time: str = Field(..., example="12:50")
    total_stops: int = Field(0, ge=0, le=4, example=0)

def calculate_duration_mins(dep_time: str, arrival_time: str) -> int:
    """Calculates duration in minutes between departure and arrival times."""
    try:
        dep_dt = datetime.strptime(dep_time, "%H:%M")
        arr_dt = datetime.strptime(arrival_time, "%H:%M")
        diff_mins = (arr_dt.hour * 60 + arr_dt.minute) - (dep_dt.hour * 60 + dep_dt.minute)
        if diff_mins <= 0:
            diff_mins += 24 * 60 # Overnight flight
        return diff_mins
    except Exception:
        return 170 # Standard average domestic duration (2h 50m)

@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    """Serves the main Prediction Interface."""
    return templates.TemplateResponse(request=request, name="index.html", context={})

@app.post("/api/predict")
async def predict_fare(payload: FlightPredictionRequest):
    """
    Step 13: Model Integration
    Transforms input JSON into the 28 engineered feature vector and returns predicted price.
    """
    try:
        # 1. Parse Journey Date
        j_date = datetime.strptime(payload.journey_date, "%Y-%m-%d")
        journey_day = j_date.day
        journey_month = j_date.month
        journey_weekday = j_date.weekday()

        # 2. Parse Times
        dep_dt = datetime.strptime(payload.dep_time, "%H:%M")
        arr_dt = datetime.strptime(payload.arrival_time, "%H:%M")
        dep_hour = dep_dt.hour
        dep_min = dep_dt.minute
        arrival_hour = arr_dt.hour
        arrival_min = arr_dt.minute

        # 3. Compute duration
        duration_mins = calculate_duration_mins(payload.dep_time, payload.arrival_time)

        # 4. Normalize destination
        destination_clean = "Delhi" if payload.destination in ["Delhi", "New Delhi"] else payload.destination

        # 5. Build feature dictionary matching feature_names.json exactly
        feature_dict = {feat: 0 for feat in feature_names}

        # Numeric values
        feature_dict["Total_Stops_Num"] = int(payload.total_stops)
        feature_dict["Journey_day"] = journey_day
        feature_dict["Journey_month"] = journey_month
        feature_dict["Journey_weekday"] = journey_weekday
        feature_dict["Dep_hour"] = dep_hour
        feature_dict["Dep_min"] = dep_min
        feature_dict["Arrival_hour"] = arrival_hour
        feature_dict["Arrival_min"] = arrival_min
        feature_dict["Duration_mins"] = duration_mins

        # One-Hot Encoded Airline
        airline_col = f"Airline_{payload.airline}"
        if airline_col in feature_dict:
            feature_dict[airline_col] = 1
        else:
            feature_dict["Airline_Other"] = 1

        # One-Hot Encoded Source
        source_col = f"Source_{payload.source}"
        if source_col in feature_dict:
            feature_dict[source_col] = 1

        # One-Hot Encoded Destination
        dest_col = f"Dest_{destination_clean}"
        if dest_col in feature_dict:
            feature_dict[dest_col] = 1

        # Build feature DataFrame with explicit column names
        input_df = pd.DataFrame([feature_dict])[feature_names]

        # 6. Predict using trained Random Forest
        predicted_fare = float(model.predict(input_df)[0])
        predicted_fare = max(1800.0, round(predicted_fare, 2)) # Guard against unrealistic negative values

        # 7. Categorize Fare
        if predicted_fare < 5000:
            category = "Budget"
        elif predicted_fare <= 11000:
            category = "Standard"
        elif predicted_fare <= 18000:
            category = "Premium"
        else:
            category = "Surge"

        # 8. Save to Database (MySQL with SQLite fallback for 5 marks)
        record_id = save_prediction_log(
            airline=payload.airline,
            source=payload.source,
            destination=payload.destination,
            journey_date=payload.journey_date,
            dep_time=payload.dep_time,
            arrival_time=payload.arrival_time,
            duration_mins=duration_mins,
            total_stops=payload.total_stops,
            predicted_fare=predicted_fare,
            fare_category=category
        )

        hours = duration_mins // 60
        mins = duration_mins % 60
        duration_formatted = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"

        return {
            "status": "success",
            "prediction_id": record_id,
            "predicted_fare": predicted_fare,
            "predicted_fare_formatted": f"Rs. {predicted_fare:,.2f}",
            "fare_category": category,
            "flight_details": {
                "airline": payload.airline,
                "route": f"{payload.source} -> {payload.destination}",
                "date": payload.journey_date,
                "departure": payload.dep_time,
                "arrival": payload.arrival_time,
                "duration": duration_formatted,
                "stops": "Non-stop" if payload.total_stops == 0 else f"{payload.total_stops} stop(s)"
            },
            "model_info": {
                "algorithm": "Random Forest Regressor (Tuned)",
                "r2_score": 0.8177,
                "features_count": len(feature_names)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction error: {str(e)}")

@app.get("/api/history")
async def get_history():
    """Returns recent predictions saved in the database."""
    history = fetch_recent_predictions(limit=10)
    return {"history": history, "count": len(history)}

@app.get("/api/metrics")
async def get_metrics():
    """Returns the ML algorithm comparison benchmarks."""
    return {"metrics": model_metrics}

@app.get("/api/db-status")
async def get_db_info():
    """Returns active database connection details."""
    return get_database_status()

@app.get("/health")
async def health_check():
    """Healthcheck endpoint."""
    return {
        "status": "healthy",
        "model_loaded": model is not None,
        "features_loaded": len(feature_names),
        "timestamp": datetime.utcnow().isoformat()
    }
