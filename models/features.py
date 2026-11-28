"""Shared feature-engineering utilities for Airfare Price Estimation.

Matches the 13-feature Kaggle pipeline (lokii1929/airfare-prediction) while
preventing data leakage by keeping all categorical encoding inside an sklearn Pipeline.
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

CATEGORICAL_COLUMNS: List[str] = [
    "Airline",
    "Source",
    "Destination",
    "Route",
    "Additional_Info",
]

NUMERICAL_COLUMNS: List[str] = [
    "Duration",
    "Total_Stops",
    "Journey_Day",
    "Journey_Month",
    "Dep_Hour",
    "Dep_Minute",
    "Arrival_Hour",
    "Arrival_Minute",
]

FEATURE_COLUMNS: List[str] = CATEGORICAL_COLUMNS + NUMERICAL_COLUMNS

AIRPORT_CODES: Dict[str, Dict[str, str]] = {
    "Banglore": {"code": "BLR", "display": "Bangalore", "state": "Karnataka"},
    "Delhi": {"code": "DEL", "display": "Delhi", "state": "National Capital Region"},
    "New Delhi": {"code": "DEL", "display": "New Delhi", "state": "National Capital Region"},
    "Kolkata": {"code": "CCU", "display": "Kolkata", "state": "West Bengal"},
    "Chennai": {"code": "MAA", "display": "Chennai", "state": "Tamil Nadu"},
    "Mumbai": {"code": "BOM", "display": "Mumbai", "state": "Maharashtra"},
    "Cochin": {"code": "COK", "display": "Cochin", "state": "Kerala"},
    "Hyderabad": {"code": "HYD", "display": "Hyderabad", "state": "Telangana"},
}

TRAINED_CORRIDORS: Set[Tuple[str, str]] = {
    ("Banglore", "Delhi"),
    ("Banglore", "New Delhi"),
    ("Chennai", "Kolkata"),
    ("Delhi", "Cochin"),
    ("Kolkata", "Banglore"),
    ("Mumbai", "Hyderabad"),
}


def parse_duration_minutes(duration: str) -> int:
    """Parse duration strings like '2h 50m', '19h', or '5m' into total integer minutes."""
    text = str(duration or "")
    hours_match = re.search(r"(\d+)h", text)
    mins_match = re.search(r"(\d+)m", text)
    hours = int(hours_match.group(1)) if hours_match else 0
    mins = int(mins_match.group(1)) if mins_match else 0
    return hours * 60 + mins


def calculate_duration_minutes(dep_time: str, arrival_time: str) -> int:
    """Compute flight duration in minutes from HH:MM strings, handling overnight flights."""
    dep_dt = datetime.strptime(dep_time, "%H:%M")
    arr_dt = datetime.strptime(arrival_time, "%H:%M")
    diff = (arr_dt.hour * 60 + arr_dt.minute) - (dep_dt.hour * 60 + dep_dt.minute)
    if diff <= 0:
        diff += 24 * 60
    return diff


def reverse_route_string(route: str) -> str:
    """Reverse layover route legs (e.g., 'DEL → BOM → COK' -> 'COK → BOM → DEL')."""
    parts = [p.strip() for p in str(route).split("→") if p.strip()]
    if len(parts) <= 1:
        return route
    return " → ".join(reversed(parts))


def preprocess_raw_dataframe(df_raw: pd.DataFrame, is_train: bool = True) -> pd.DataFrame:
    """Clean and transform raw flight Excel/CSV dataframe into engineered features."""
    df = df_raw.copy()
    if is_train:
        df.dropna(inplace=True)
        df.drop_duplicates(inplace=True)

    journey_dt = pd.to_datetime(df["Date_of_Journey"], format="mixed", dayfirst=True)
    df["Journey_Day"] = journey_dt.dt.day.astype(int)
    df["Journey_Month"] = journey_dt.dt.month.astype(int)
    df["Journey_Weekday"] = journey_dt.dt.weekday.astype(int)
    df.drop("Date_of_Journey", axis=1, inplace=True)

    df["Dep_Hour"] = df["Dep_Time"].astype(str).str.extract(r"(\d{1,2}):").astype(int)
    df["Dep_Minute"] = df["Dep_Time"].astype(str).str.extract(r":(\d{2})").astype(int)
    df["Arrival_Hour"] = df["Arrival_Time"].astype(str).str.extract(r"(\d{1,2}):").astype(int)
    df["Arrival_Minute"] = df["Arrival_Time"].astype(str).str.extract(r":(\d{2})").astype(int)
    df.drop(["Dep_Time", "Arrival_Time"], axis=1, inplace=True)

    df["Duration"] = df["Duration"].apply(parse_duration_minutes).astype(int)
    df["Total_Stops"] = (
        df["Total_Stops"].astype(str).str.extract(r"(\d+)").fillna(0).astype(int)
    )
    return df


def resolve_route_string(
    source: str,
    destination: str,
    total_stops: int,
    requested_route: Optional[str],
    route_catalog: Dict,
) -> str:
    """Resolve an explicit route or look up a stop-consistent historical/synthetic route."""
    if requested_route and requested_route.strip() and requested_route.strip().lower() != "auto":
        return requested_route.strip()

    stops = max(0, int(total_stops))
    norm_src = "Delhi" if source == "New Delhi" else source
    routes_map = route_catalog.get("routes_by_trip", {})

    # 1. Exact stop-count historical route (includes mirrored pairs from catalog)
    key = f"{norm_src}|{destination}|{stops}"
    candidates = routes_map.get(key)
    if candidates:
        return candidates[0]["route"]

    # 2. Reverse corridor with identical stop count
    norm_dst = "Delhi" if destination == "New Delhi" else destination
    rev_key = f"{norm_dst}|{norm_src}|{stops}"
    if routes_map.get(rev_key):
        return reverse_route_string(routes_map[rev_key][0]["route"])

    # 3. Construct exact-stop fallback path avoiding origin/destination hubs
    src_code = AIRPORT_CODES.get(source, {}).get("code", source[:3].upper())
    dst_code = AIRPORT_CODES.get(destination, {}).get("code", destination[:3].upper())
    if stops == 0:
        return f"{src_code} → {dst_code}"

    hub_pool = [h for h in ("BOM", "DEL", "BLR", "HYD", "CCU", "MAA") if h not in {src_code, dst_code}]
    selected_hubs = hub_pool[:stops]
    return " → ".join([src_code, *selected_hubs, dst_code])


def build_inference_dataframe(
    airline: str,
    source: str,
    destination: str,
    journey_date: str,
    dep_time: str,
    arrival_time: str,
    total_stops: int,
    route: Optional[str] = None,
    additional_info: str = "No info",
    duration_override_mins: Optional[int] = None,
    route_catalog: Optional[Dict] = None,
) -> Tuple[pd.DataFrame, str, int]:
    """Construct a single-row DataFrame matching FEATURE_COLUMNS for Pipeline inference.

    Applies bidirectional corridor symmetry when evaluating reverse directions of
    trained corridors (e.g., Cochin -> Delhi mirrors Delhi -> Cochin) so predictions
    retain trained route and hub fidelity.
    """
    j_dt = datetime.strptime(journey_date, "%Y-%m-%d")
    dep_dt = datetime.strptime(dep_time, "%H:%M")
    arr_dt = datetime.strptime(arrival_time, "%H:%M")

    duration_mins = (
        int(duration_override_mins)
        if duration_override_mins is not None and duration_override_mins > 0
        else calculate_duration_minutes(dep_time, arrival_time)
    )
    resolved_route = resolve_route_string(
        source, destination, total_stops, route, route_catalog or {}
    )
    clean_info = (additional_info or "No info").strip() or "No info"

    model_src = "Delhi" if source == "New Delhi" else source
    model_dst = destination
    model_route = resolved_route

    if (model_src, model_dst) not in TRAINED_CORRIDORS:
        reverse_dst = "Delhi" if model_dst == "New Delhi" else model_dst
        if (reverse_dst, model_src) in TRAINED_CORRIDORS:
            model_src, model_dst = reverse_dst, model_src
            model_route = reverse_route_string(resolved_route)
        elif (reverse_dst, "New Delhi") in TRAINED_CORRIDORS and model_src == "Banglore":
            model_src, model_dst = reverse_dst, "New Delhi"
            model_route = reverse_route_string(resolved_route)

    row = {
        "Airline": airline,
        "Source": model_src,
        "Destination": model_dst,
        "Route": model_route,
        "Additional_Info": clean_info,
        "Duration": duration_mins,
        "Total_Stops": int(total_stops),
        "Journey_Day": j_dt.day,
        "Journey_Month": j_dt.month,
        "Dep_Hour": dep_dt.hour,
        "Dep_Minute": dep_dt.minute,
        "Arrival_Hour": arr_dt.hour,
        "Arrival_Minute": arr_dt.minute,
    }
    return pd.DataFrame([row], columns=FEATURE_COLUMNS), resolved_route, duration_mins
