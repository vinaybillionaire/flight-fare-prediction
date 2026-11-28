"""FastAPI Backend Application for FareLens.

Project: Airfare Price Estimation and Fare Pattern Analysis-II (Group G1716)
Includes:
- Leak-free 90%+ R2 Random Forest Pipeline with IQR Confidence Interval
- Batch 7-Day Date Flexibility & Cross-Airline Comparison Inference
- JWT Authentication & Role-Based Access Control (Traveler, Analyst, Admin)
- Normalized 3NF Database Full CRUD (Predictions + Fare Watchlist Alerts + Catalog)
- Real EDA Analytics, Model Benchmarks & Market Drift Insights
"""

import csv
import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

import joblib
import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.auth import (
    create_access_token,
    get_current_user,
    get_optional_user,
    hash_password,
    require_roles,
    verify_password,
)
from database.db import (
    CITY_TO_IATA,
    add_airline_catalog,
    create_fare_alert,
    create_user,
    delete_fare_alert,
    delete_prediction_record,
    fetch_fare_alerts,
    fetch_recent_predictions,
    get_database_status,
    get_master_catalog,
    get_user_by_email,
    list_all_users,
    save_prediction_log,
    sync_model_benchmarks,
    update_fare_alert,
    update_prediction_notes,
    update_user_admin,
)
from models.features import (
    FEATURE_COLUMNS,
    build_inference_dataframe,
    calculate_duration_minutes,
    resolve_route_string,
)

MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
MODEL_PATH = os.path.join(MODELS_DIR, "flight_rf_model.pkl")
METRICS_PATH = os.path.join(MODELS_DIR, "model_metrics.json")
EDA_PATH = os.path.join(MODELS_DIR, "eda_summary.json")
CATALOG_PATH = os.path.join(MODELS_DIR, "route_catalog.json")


def _load_json(path: str, default: dict) -> dict:
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default


if not os.path.exists(MODEL_PATH):
    raise RuntimeError(
        f"Trained ML pipeline not found at {MODEL_PATH}. Run 'python3 models/train_models.py' first."
    )

model_pipeline = joblib.load(MODEL_PATH)
model_metrics = _load_json(METRICS_PATH, {})
eda_summary = _load_json(EDA_PATH, {})
route_catalog = _load_json(CATALOG_PATH, {})
sync_model_benchmarks(model_metrics)

SELECTED_MODEL_NAME = model_metrics.get("selected_model", "Random Forest (Kaggle Base)")
SELECTED_MODEL_STATS = model_metrics.get("models", {}).get(
    SELECTED_MODEL_NAME, {"r2_score": 0.9021, "mae": 620.34, "rmse": 1428.78}
)

app = FastAPI(
    title="FareLens — Airfare Intelligence & ML Estimation API",
    description="High-accuracy (90%+ R2) Random Forest flight fare platform with RBAC, 3NF CRUD, EDA, and fare flexibility.",
    version="3.0.0",
)

STATIC_DIR = os.path.join(PROJECT_ROOT, "frontend", "static")
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "frontend", "templates")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# ---------------------- Request Schemas ----------------------
class RegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=5, max_length=150)
    password: str = Field(..., min_length=6, max_length=100)
    role: Literal["traveler", "analyst"] = "traveler"

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        val = v.strip().lower()
        if "@" not in val or "." not in val.split("@")[-1]:
            raise ValueError("Please provide a valid email address.")
        return val


class LoginRequest(BaseModel):
    email: str
    password: str


IST_TZ = timezone(timedelta(hours=5, minutes=30))


def _validate_upcoming_journey_date(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("journey_date must follow YYYY-MM-DD format.")
    if parsed < datetime.now(IST_TZ).date():
        raise ValueError("Departure date cannot be in the past. Please select today or a future date.")
    return value


class FlightPredictionRequest(BaseModel):
    airline: str = Field(..., min_length=2, max_length=80)
    source: str = Field(..., min_length=2, max_length=60)
    destination: str = Field(..., min_length=2, max_length=60)
    journey_date: str = Field(..., description="YYYY-MM-DD")
    dep_time: str = Field(..., description="HH:MM")
    arrival_time: str = Field(..., description="HH:MM")
    total_stops: int = Field(0, ge=0, le=4)
    route: Optional[str] = Field(default="auto")
    additional_info: str = Field(default="No info")
    inflation_factor: float = Field(default=1.0, ge=1.0, le=1.6)
    notes: str = Field(default="", max_length=255)

    @field_validator("journey_date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        return _validate_upcoming_journey_date(v)

    @field_validator("dep_time", "arrival_time")
    @classmethod
    def validate_time(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%H:%M")
        except ValueError:
            raise ValueError("Time fields must follow HH:MM (24-hour) format.")
        return v


class UpdatePredictionNotesRequest(BaseModel):
    notes: str = Field(..., max_length=255)


class FareAlertCreateRequest(BaseModel):
    prediction_id: Optional[int] = None
    airline: str = Field(..., min_length=2, max_length=80)
    source: str = Field(..., min_length=2, max_length=60)
    destination: str = Field(..., min_length=2, max_length=60)
    journey_date: str
    target_price: float = Field(..., gt=0, le=500000)
    estimated_price: float = Field(..., gt=0, le=500000)
    notes: str = Field(default="", max_length=255)

    @field_validator("journey_date")
    @classmethod
    def validate_alert_date(cls, v: str) -> str:
        return _validate_upcoming_journey_date(v)


class FareAlertUpdateRequest(BaseModel):
    target_price: Optional[float] = Field(default=None, gt=0, le=500000)
    status: Optional[Literal["watching", "target_met", "paused"]] = None
    notes: Optional[str] = Field(default=None, max_length=255)


class AdminUserUpdateRequest(BaseModel):
    role: Optional[Literal["traveler", "analyst", "admin"]] = None
    is_active: Optional[bool] = None


class AdminAirlineCreateRequest(BaseModel):
    airline_name: str = Field(..., min_length=2, max_length=100)
    carrier_code: str = Field(..., min_length=2, max_length=10)
    airline_tier: str = Field(default="Full-Service", max_length=40)


# ---------------------- Inference Helpers ----------------------
def _validate_trip_pair(source: str, destination: str) -> None:
    src_code = CITY_TO_IATA.get(source, source)
    dst_code = CITY_TO_IATA.get(destination, destination)
    if src_code == dst_code:
        raise HTTPException(
            status_code=422,
            detail="Origin and destination cities refer to the same airport. Select two different cities.",
        )


def _predict_with_interval(input_df: pd.DataFrame) -> tuple[float, float, float]:
    """Run Random Forest Pipeline and compute IQR prediction band across trees."""
    prep = model_pipeline.named_steps["prep"]
    rf = model_pipeline.named_steps["model"]
    transformed = prep.transform(input_df)
    tree_preds = np.array([tree.predict(transformed)[0] for tree in rf.estimators_])
    mean_pred = max(1750.0, float(tree_preds.mean()))
    lower = max(1750.0, float(np.percentile(tree_preds, 25)))
    upper = max(mean_pred, float(np.percentile(tree_preds, 75)))
    return round(mean_pred, 2), round(lower, 2), round(upper, 2)


def _categorize_fare(fare: float) -> str:
    if fare < 5000:
        return "Budget"
    if fare <= 11000:
        return "Standard"
    if fare <= 18000:
        return "Premium"
    return "Surge"


def _build_prediction_factors(
    payload: FlightPredictionRequest,
    duration_mins: int,
    predicted_fare: float,
) -> list[dict]:
    """Explain key fare drivers for this specific prediction."""
    factors = []
    if payload.total_stops == 0:
        factors.append({"factor": "Non-stop convenience", "impact": "Lower layover overhead", "tone": "positive"})
    elif payload.total_stops == 1:
        factors.append({"factor": "1 Layover Stop", "impact": "Adds layover routing premium vs direct", "tone": "neutral"})
    else:
        factors.append({"factor": f"{payload.total_stops} Stops", "impact": "Multi-leg itinerary increases fare variance", "tone": "warning"})

    if duration_mins >= 600:
        factors.append({"factor": f"Long Duration ({duration_mins // 60}h {duration_mins % 60}m)", "impact": "Top feature (~42% importance weight)", "tone": "warning"})
    else:
        factors.append({"factor": f"Flight Duration ({duration_mins // 60}h {duration_mins % 60}m)", "impact": "Short/medium haul duration", "tone": "positive"})

    if "Business" in payload.airline or payload.additional_info == "Business class":
        factors.append({"factor": "Business Cabin", "impact": "Premium class multiplier", "tone": "warning"})
    elif payload.additional_info == "In-flight meal not included":
        factors.append({"factor": "No In-Flight Meal", "impact": "Distinct fare bucket in 2019 dataset", "tone": "neutral"})

    j_dt = datetime.strptime(payload.journey_date, "%Y-%m-%d")
    if j_dt.weekday() >= 4:
        factors.append({"factor": j_dt.strftime("%A Departure"), "impact": "Weekend demand window", "tone": "warning"})
    else:
        factors.append({"factor": j_dt.strftime("%A Departure"), "impact": "Mid-week travel window", "tone": "positive"})

    if predicted_fare > 14000:
        factors.append({"factor": "High Fare Alert", "impact": "Check 7-day calendar for cheaper dates", "tone": "warning"})
    return factors


# ---------------------- Page & Health Routes ----------------------
@app.get("/", response_class=HTMLResponse)
@app.get("/api", response_class=HTMLResponse)
@app.get("/api/index.py", response_class=HTMLResponse)
async def serve_home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.get("/health")
async def health_check():
    db_info = get_database_status()
    return {
        "status": "healthy",
        "model_loaded": model_pipeline is not None,
        "selected_model": SELECTED_MODEL_NAME,
        "r2_score": SELECTED_MODEL_STATS.get("r2_score"),
        "raw_features": len(FEATURE_COLUMNS),
        "encoded_features": model_metrics.get("encoded_feature_count", 169),
        "database_status": db_info["status"],
        "database_type": db_info["db_type"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/catalog")
async def get_catalog():
    return {
        "catalog": route_catalog,
        "master": get_master_catalog(),
    }


# ---------------------- Auth Routes ----------------------
@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
async def register_user(payload: RegisterRequest):
    try:
        user = create_user(
            full_name=payload.full_name,
            email=payload.email,
            password_hash=hash_password(payload.password),
            role=payload.role,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))

    token = create_access_token(user["id"], user["email"], user["role"], user["full_name"])
    return {"access_token": token, "token_type": "bearer", "user": user}


@app.post("/api/auth/login")
async def login_user(payload: LoginRequest):
    user_row = get_user_by_email(payload.email)
    if not user_row or not verify_password(payload.password, user_row.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not user_row.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated by an administrator.",
        )
    token = create_access_token(
        user_row.id, user_row.email, user_row.role, user_row.full_name
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user_row.id,
            "full_name": user_row.full_name,
            "email": user_row.email,
            "role": user_row.role,
            "is_active": bool(user_row.is_active),
        },
    }


@app.get("/api/auth/me")
async def read_current_user(user: dict = Depends(get_current_user)):
    return {"user": user}


# ---------------------- ML Inference & Comparison Routes ----------------------
@app.post("/api/predict")
@app.post("/predict")
async def predict_fare(
    payload: FlightPredictionRequest,
    user: Optional[dict] = Depends(get_optional_user),
):
    _validate_trip_pair(payload.source, payload.destination)

    input_df, resolved_route, duration_mins = build_inference_dataframe(
        airline=payload.airline,
        source=payload.source,
        destination=payload.destination,
        journey_date=payload.journey_date,
        dep_time=payload.dep_time,
        arrival_time=payload.arrival_time,
        total_stops=payload.total_stops,
        route=payload.route,
        additional_info=payload.additional_info,
        route_catalog=route_catalog,
    )

    historical_fare, lower_bound, upper_bound = _predict_with_interval(input_df)
    adjusted_fare = round(historical_fare * payload.inflation_factor, 2)
    adjusted_lower = round(lower_bound * payload.inflation_factor, 2)
    adjusted_upper = round(upper_bound * payload.inflation_factor, 2)
    category = _categorize_fare(adjusted_fare)

    record_id = save_prediction_log(
        airline=payload.airline,
        source=payload.source,
        destination=payload.destination,
        route_str=resolved_route,
        additional_info=payload.additional_info,
        journey_date=payload.journey_date,
        dep_time=payload.dep_time,
        arrival_time=payload.arrival_time,
        duration_mins=duration_mins,
        total_stops=payload.total_stops,
        predicted_fare=adjusted_fare,
        fare_lower=adjusted_lower,
        fare_upper=adjusted_upper,
        fare_category=category,
        model_name=SELECTED_MODEL_NAME,
        model_r2_score=SELECTED_MODEL_STATS.get("r2_score", 0.9021),
        user_id=user["id"] if user else None,
        notes=payload.notes,
    )

    hours, mins = duration_mins // 60, duration_mins % 60
    duration_formatted = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"

    return {
        "status": "success",
        "prediction_id": record_id,
        "predicted_fare": adjusted_fare,
        "historical_2019_fare": historical_fare,
        "inflation_factor": payload.inflation_factor,
        "confidence_interval": {"lower": adjusted_lower, "upper": adjusted_upper},
        "fare_category": category,
        "flight_details": {
            "airline": payload.airline,
            "source": payload.source,
            "destination": payload.destination,
            "route": f"{payload.source} -> {payload.destination}",
            "resolved_route_path": resolved_route,
            "additional_info": payload.additional_info,
            "date": payload.journey_date,
            "departure": payload.dep_time,
            "arrival": payload.arrival_time,
            "duration": duration_formatted,
            "duration_mins": duration_mins,
            "stops": "Non-stop" if payload.total_stops == 0 else f"{payload.total_stops} stop(s)",
        },
        "drivers": _build_prediction_factors(payload, duration_mins, adjusted_fare),
        "model_info": {
            "algorithm": SELECTED_MODEL_NAME,
            "r2_score": SELECTED_MODEL_STATS.get("r2_score"),
            "mae": SELECTED_MODEL_STATS.get("mae"),
            "rmse": SELECTED_MODEL_STATS.get("rmse"),
            "features_count": model_metrics.get("encoded_feature_count", 169),
        },
    }


@app.post("/api/compare-dates")
async def compare_flexible_dates(payload: FlightPredictionRequest):
    """Evaluate +/- 3 days around journey_date in a single vectorized ML batch."""
    _validate_trip_pair(payload.source, payload.destination)
    base_dt = datetime.strptime(payload.journey_date, "%Y-%m-%d")
    duration_mins = calculate_duration_minutes(payload.dep_time, payload.arrival_time)
    resolved_route = resolve_route_string(
        payload.source, payload.destination, payload.total_stops, payload.route, route_catalog
    )

    rows = []
    dates_meta = []
    today_dt = datetime.combine(datetime.now(IST_TZ).date(), datetime.min.time())
    start_dt = max(today_dt, base_dt - timedelta(days=3))
    for offset in range(7):
        d = start_dt + timedelta(days=offset)
        df_row, _, _ = build_inference_dataframe(
            airline=payload.airline,
            source=payload.source,
            destination=payload.destination,
            journey_date=d.strftime("%Y-%m-%d"),
            dep_time=payload.dep_time,
            arrival_time=payload.arrival_time,
            total_stops=payload.total_stops,
            route=resolved_route,
            additional_info=payload.additional_info,
            duration_override_mins=duration_mins,
            route_catalog=route_catalog,
        )
        rows.append(df_row)
        dates_meta.append(
            {
                "date": d.strftime("%Y-%m-%d"),
                "label": d.strftime("%d %b (%a)"),
                "is_selected": d.date() == base_dt.date(),
            }
        )

    batch_df = pd.concat(rows, ignore_index=True)
    preds = model_pipeline.predict(batch_df)
    results = []
    for meta, raw_pred in zip(dates_meta, preds):
        fare = round(max(1750.0, float(raw_pred)) * payload.inflation_factor, 2)
        results.append({**meta, "predicted_fare": fare})

    cheapest = min(results, key=lambda x: x["predicted_fare"])
    selected = next(x for x in results if x["is_selected"])
    savings = round(selected["predicted_fare"] - cheapest["predicted_fare"], 2)
    return {
        "dates": results,
        "cheapest_date": cheapest["date"],
        "cheapest_fare": cheapest["predicted_fare"],
        "potential_savings": max(0.0, savings),
    }


@app.post("/api/compare-airlines")
async def compare_airlines(payload: FlightPredictionRequest):
    """Compare predicted fares and fixed airline schedules across major domestic carriers."""
    _validate_trip_pair(payload.source, payload.destination)
    norm_src = "Delhi" if payload.source == "New Delhi" else payload.source
    schedules_map = route_catalog.get("schedules_by_pair", {})
    default_sched_map = route_catalog.get("default_schedules_by_airline", {})

    airlines_to_compare = [
        "Air Asia",
        "SpiceJet",
        "IndiGo",
        "GoAir",
        "Vistara",
        "Air India",
        "Multiple carriers",
        "Jet Airways",
    ]
    if payload.airline not in airlines_to_compare:
        airlines_to_compare.append(payload.airline)

    rows = []
    meta_list = []
    for carrier in airlines_to_compare:
        if carrier == payload.airline:
            c_dep = payload.dep_time
            c_arr = payload.arrival_time
            c_stops = int(payload.total_stops)
            c_route = payload.route
            c_dur = calculate_duration_minutes(c_dep, c_arr)
        else:
            pair_scheds = (
                schedules_map.get(f"{payload.source}|{payload.destination}|{carrier}")
                or schedules_map.get(f"{norm_src}|{payload.destination}|{carrier}")
                or []
            )
            # Prefer a schedule matching the selected stop count if available, else top primary slot
            chosen = next((s for s in pair_scheds if s["total_stops"] == payload.total_stops), None)
            if not chosen and pair_scheds:
                chosen = pair_scheds[0]
            if not chosen:
                fallback = default_sched_map.get(carrier, [])
                chosen = fallback[0] if fallback else None

            if chosen:
                c_dep = chosen["dep_time"]
                c_arr = chosen["arrival_time"]
                c_stops = int(chosen["total_stops"])
                c_route = chosen.get("route") or "auto"
                c_dur = int(chosen["duration_mins"])
            else:
                c_dep = payload.dep_time
                c_arr = payload.arrival_time
                c_stops = int(payload.total_stops)
                c_route = payload.route
                c_dur = calculate_duration_minutes(c_dep, c_arr)

        df_row, resolved_route, dur_mins = build_inference_dataframe(
            airline=carrier,
            source=payload.source,
            destination=payload.destination,
            journey_date=payload.journey_date,
            dep_time=c_dep,
            arrival_time=c_arr,
            total_stops=c_stops,
            route=c_route,
            additional_info=payload.additional_info,
            duration_override_mins=c_dur,
            route_catalog=route_catalog,
        )
        rows.append(df_row)
        hrs, mins = dur_mins // 60, dur_mins % 60
        meta_list.append(
            {
                "airline": carrier,
                "dep_time": c_dep,
                "arrival_time": c_arr,
                "duration_mins": dur_mins,
                "duration": f"{hrs}h {mins}m" if hrs > 0 else f"{mins}m",
                "total_stops": c_stops,
                "stops_label": "Non-stop" if c_stops == 0 else f"{c_stops} stop(s)",
                "resolved_route": resolved_route,
            }
        )

    batch_df = pd.concat(rows, ignore_index=True)
    preds = model_pipeline.predict(batch_df)
    comparisons = []
    for meta, raw_pred in zip(meta_list, preds):
        fare = round(max(1750.0, float(raw_pred)) * payload.inflation_factor, 2)
        comparisons.append(
            {
                **meta,
                "predicted_fare": fare,
                "fare_category": _categorize_fare(fare),
                "is_selected": meta["airline"] == payload.airline,
            }
        )
    comparisons.sort(key=lambda x: x["predicted_fare"])
    selected_meta = next((c for c in comparisons if c["is_selected"]), comparisons[0])
    return {"comparisons": comparisons, "resolved_route": selected_meta["resolved_route"]}


# ---------------------- History & Prediction CRUD ----------------------
@app.get("/api/history")
async def get_history(
    limit: int = Query(default=25, ge=1, le=100),
    airline: Optional[str] = None,
    search: Optional[str] = None,
    mine: bool = False,
    user: Optional[dict] = Depends(get_optional_user),
):
    uid = user["id"] if (mine and user) else None
    history = fetch_recent_predictions(
        limit=limit, user_id=uid, airline=airline, search=search
    )
    return {"history": history, "count": len(history)}


def _workspace_actor(user: Optional[dict]) -> dict:
    """Resolve authenticated user or fall back to seeded public workspace account."""
    if user is not None:
        return user
    default_user = get_user_by_email("traveler@farelens.in")
    if default_user is not None:
        return {
            "id": default_user.id,
            "email": default_user.email,
            "role": default_user.role,
            "full_name": default_user.full_name,
        }
    return {"id": 1, "email": "guest@farelens.in", "role": "traveler", "full_name": "Guest"}


@app.patch("/api/history/{prediction_id}")
async def edit_prediction_notes(
    prediction_id: int,
    payload: UpdatePredictionNotesRequest,
    user: Optional[dict] = Depends(get_optional_user),
):
    actor = _workspace_actor(user)
    try:
        updated = update_prediction_notes(
            prediction_id=prediction_id,
            notes=payload.notes,
            requester_id=actor["id"],
            requester_role=actor["role"],
        )
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction record not found.")
    return {"status": "updated", "record": updated}


@app.delete("/api/history/{prediction_id}")
async def remove_prediction_record(
    prediction_id: int,
    user: Optional[dict] = Depends(get_optional_user),
):
    actor = _workspace_actor(user)
    try:
        deleted = delete_prediction_record(
            prediction_id=prediction_id,
            requester_id=actor["id"],
            requester_role=actor["role"],
        )
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction record not found.")
    return {"status": "deleted", "id": prediction_id}


@app.get("/api/history/export")
async def export_history_csv():
    rows = fetch_recent_predictions(limit=500)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "ID",
            "Timestamp",
            "User",
            "Airline",
            "Source",
            "Destination",
            "Route",
            "Journey_Date",
            "Stops",
            "Duration_Mins",
            "Predicted_Fare_INR",
            "Category",
            "Notes",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r["id"],
                r["timestamp"],
                r["user_email"],
                r["airline"],
                r["source"],
                r["destination"],
                r["route_str"],
                r["journey_date"],
                r["total_stops"],
                r["duration_mins"],
                r["predicted_fare"],
                r["fare_category"],
                r["notes"],
            ]
        )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=farelens_predictions.csv"},
    )


# ---------------------- Fare Watchlist Alerts CRUD ----------------------
@app.get("/api/alerts")
async def list_alerts(user: Optional[dict] = Depends(get_optional_user)):
    actor = _workspace_actor(user)
    alerts = fetch_fare_alerts(
        user_id=actor["id"], is_admin=(actor["role"] == "admin")
    )
    return {"alerts": alerts, "count": len(alerts)}


@app.post("/api/alerts", status_code=status.HTTP_201_CREATED)
async def create_alert(
    payload: FareAlertCreateRequest,
    user: Optional[dict] = Depends(get_optional_user),
):
    _validate_trip_pair(payload.source, payload.destination)
    actor = _workspace_actor(user)
    try:
        alert = create_fare_alert(
            user_id=actor["id"],
            airline=payload.airline,
            source=payload.source,
            destination=payload.destination,
            journey_date=payload.journey_date,
            target_price=payload.target_price,
            estimated_price=payload.estimated_price,
            prediction_id=payload.prediction_id,
            notes=payload.notes,
        )
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))
    return {"status": "created", "alert": alert}


@app.patch("/api/alerts/{alert_id}")
async def edit_alert(
    alert_id: int,
    payload: FareAlertUpdateRequest,
    user: Optional[dict] = Depends(get_optional_user),
):
    actor = _workspace_actor(user)
    try:
        updated = update_fare_alert(
            alert_id=alert_id,
            user_id=actor["id"],
            is_admin=(actor["role"] == "admin"),
            target_price=payload.target_price,
            status_val=payload.status,
            notes=payload.notes,
        )
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fare alert not found.")
    return {"status": "updated", "alert": updated}


@app.delete("/api/alerts/{alert_id}")
async def remove_alert(alert_id: int, user: Optional[dict] = Depends(get_optional_user)):
    actor = _workspace_actor(user)
    try:
        deleted = delete_fare_alert(
            alert_id=alert_id,
            user_id=actor["id"],
            is_admin=(actor["role"] == "admin"),
        )
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fare alert not found.")
    return {"status": "deleted", "id": alert_id}


# ---------------------- Analytics, Benchmarks & Admin Routes ----------------------
@app.get("/api/analytics")
async def get_analytics():
    return {"eda": eda_summary}


@app.get("/api/metrics")
async def get_metrics():
    return {"metrics": model_metrics}


@app.get("/api/db-status")
async def get_db_info():
    return get_database_status()


@app.get("/api/admin/users")
async def admin_list_users(_admin: dict = Depends(require_roles("admin"))):
    return {"users": list_all_users()}


@app.patch("/api/admin/users/{user_id}")
async def admin_update_user(
    user_id: int,
    payload: AdminUserUpdateRequest,
    admin: dict = Depends(require_roles("admin")),
):
    if user_id == admin["id"] and payload.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin cannot deactivate their own active session.",
        )
    updated = update_user_admin(user_id, role=payload.role, is_active=payload.is_active)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return {"status": "updated", "user": updated}


@app.post("/api/admin/airlines", status_code=status.HTTP_201_CREATED)
async def admin_add_airline(
    payload: AdminAirlineCreateRequest,
    _admin: dict = Depends(require_roles("admin")),
):
    try:
        item = add_airline_catalog(
            payload.airline_name, payload.carrier_code, payload.airline_tier
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
    return {"status": "created", "airline": item}
