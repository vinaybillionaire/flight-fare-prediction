"""Unified Database Facade for FareLens.

Automatically selects MongoDB (when MONGODB_URI or DB_ENGINE=mongodb is active)
or the 3NF SQL Engine (MySQL primary with zero-config SQLite 3NF fallback).
Also loads local `.env` variables if present.
"""

import os
from typing import Dict, List, Optional

from database.sql_store import SQLStore

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_dotenv(env_path: str) -> None:
    if not os.path.exists(env_path):
        return
    with open(env_path, "r") as fp:
        for raw_line in fp:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


_load_dotenv(os.path.join(BASE_DIR, ".env"))

CITY_TO_IATA = {
    "Banglore": "BLR",
    "Bangalore": "BLR",
    "Delhi": "DEL",
    "New Delhi": "DEL",
    "Kolkata": "CCU",
    "Chennai": "MAA",
    "Mumbai": "BOM",
    "Cochin": "COK",
    "Hyderabad": "HYD",
}

SEED_AIRPORTS = [
    ("BLR", "Banglore", "Karnataka"),
    ("CCU", "Kolkata", "West Bengal"),
    ("DEL", "Delhi", "National Capital Region"),
    ("MAA", "Chennai", "Tamil Nadu"),
    ("BOM", "Mumbai", "Maharashtra"),
    ("COK", "Cochin", "Kerala"),
    ("HYD", "Hyderabad", "Telangana"),
]

SEED_AIRLINES = [
    ("IndiGo", "6E", "Low-Cost Carrier"),
    ("Air India", "AI", "Full-Service"),
    ("Jet Airways", "9W", "Full-Service (Historical 2019)"),
    ("SpiceJet", "SG", "Low-Cost Carrier"),
    ("Multiple carriers", "MC", "Interline"),
    ("Vistara", "UK", "Full-Service"),
    ("Air Asia", "I5", "Low-Cost Carrier"),
    ("GoAir", "G8", "Low-Cost (Historical 2019)"),
    ("Multiple carriers Premium economy", "MC-PE", "Premium Economy"),
    ("Jet Airways Business", "9W-BUS", "Business Class"),
    ("Vistara Premium economy", "UK-PE", "Premium Economy"),
    ("Trujet", "2T", "Regional (Historical 2019)"),
]

DB_ENGINE = os.getenv("DB_ENGINE", "auto").strip().lower()
MONGODB_URI = os.getenv("MONGODB_URI", "").strip()
MONGODB_DB = os.getenv("MONGODB_DB", "flight_fare_db").strip() or "flight_fare_db"
MYSQL_URI = os.getenv("MYSQL_URI", "mysql+pymysql://root:@localhost:3306/flight_fare_db")
DB_PATH_SQLITE = (
    "/tmp/flight_fare.db"
    if os.getenv("VERCEL")
    else os.path.join(BASE_DIR, "database", "flight_fare.db")
)

_store = None
if DB_ENGINE == "mongodb" or (DB_ENGINE == "auto" and MONGODB_URI):
    effective_mongo_uri = MONGODB_URI or "mongodb://localhost:27017"
    try:
        from database.mongo_store import MongoStore

        _store = MongoStore(
            mongo_uri=effective_mongo_uri,
            db_name=MONGODB_DB,
            city_to_iata=CITY_TO_IATA,
            seed_airports=SEED_AIRPORTS,
            seed_airlines=SEED_AIRLINES,
        )
    except Exception as exc:
        if DB_ENGINE == "mongodb":
            raise RuntimeError(f"MongoDB requested via DB_ENGINE=mongodb but failed to connect: {exc}") from exc
        _store = None

if _store is None:
    _store = SQLStore(
        mysql_uri=MYSQL_URI,
        sqlite_path=DB_PATH_SQLITE,
        city_to_iata=CITY_TO_IATA,
        seed_airports=SEED_AIRPORTS,
        seed_airlines=SEED_AIRLINES,
    )


def sync_model_benchmarks(metrics_payload: Dict) -> None:
    _store.sync_model_benchmarks(metrics_payload)


def get_user_by_email(email: str):
    return _store.get_user_by_email(email)


def get_user_by_id(user_id: int) -> Optional[Dict]:
    return _store.get_user_by_id(user_id)


def create_user(full_name: str, email: str, password_hash: str, role: str = "traveler") -> Dict:
    return _store.create_user(full_name, email, password_hash, role)


def list_all_users() -> List[Dict]:
    return _store.list_all_users()


def update_user_admin(user_id: int, role: Optional[str] = None, is_active: Optional[bool] = None) -> Optional[Dict]:
    return _store.update_user_admin(user_id, role=role, is_active=is_active)


def save_prediction_log(**kwargs) -> int:
    return _store.save_prediction_log(**kwargs)


def fetch_recent_predictions(
    limit: int = 25,
    user_id: Optional[int] = None,
    airline: Optional[str] = None,
    search: Optional[str] = None,
) -> List[Dict]:
    return _store.fetch_recent_predictions(limit=limit, user_id=user_id, airline=airline, search=search)


def update_prediction_notes(
    prediction_id: int, notes: str, requester_id: int, requester_role: str
) -> Optional[Dict]:
    return _store.update_prediction_notes(prediction_id, notes, requester_id, requester_role)


def delete_prediction_record(prediction_id: int, requester_id: int, requester_role: str) -> bool:
    return _store.delete_prediction_record(prediction_id, requester_id, requester_role)


def create_fare_alert(**kwargs) -> Dict:
    return _store.create_fare_alert(**kwargs)


def fetch_fare_alerts(user_id: Optional[int] = None, is_admin: bool = False) -> List[Dict]:
    return _store.fetch_fare_alerts(user_id=user_id, is_admin=is_admin)


def update_fare_alert(
    alert_id: int,
    user_id: int,
    is_admin: bool,
    target_price: Optional[float] = None,
    status_val: Optional[str] = None,
    notes: Optional[str] = None,
) -> Optional[Dict]:
    return _store.update_fare_alert(
        alert_id, user_id, is_admin, target_price=target_price, status_val=status_val, notes=notes
    )


def delete_fare_alert(alert_id: int, user_id: int, is_admin: bool) -> bool:
    return _store.delete_fare_alert(alert_id, user_id, is_admin)


def get_master_catalog() -> Dict:
    return _store.get_master_catalog()


def add_airline_catalog(airline_name: str, carrier_code: str, airline_tier: str) -> Dict:
    return _store.add_airline_catalog(airline_name, carrier_code, airline_tier)


def get_database_status() -> Dict:
    return _store.get_database_status()
