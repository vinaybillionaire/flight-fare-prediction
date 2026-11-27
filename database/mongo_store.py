"""MongoDB Persistence Adapter for FareLens (pymongo).

Provides full schema-indexed collection parity and CRUD semantics with the
3NF SQL backend so deployments can persist directly to MongoDB Atlas or local mongod.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Dict, List, Optional

import bcrypt
from pymongo import DESCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

try:
    import certifi
except ImportError:
    certifi = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_seed_pw(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


class MongoStore:
    def __init__(
        self,
        mongo_uri: str,
        db_name: str,
        city_to_iata: Dict[str, str],
        seed_airports: List[tuple],
        seed_airlines: List[tuple],
    ):
        self.mongo_uri = mongo_uri
        self.db_name = db_name
        self.city_to_iata = city_to_iata
        client_kwargs = {
            "serverSelectionTimeoutMS": 8000,
            "connectTimeoutMS": 8000,
            "socketTimeoutMS": 15000,
        }
        lowered_uri = mongo_uri.lower()
        if certifi is not None and (
            "mongodb+srv://" in lowered_uri or "tls=true" in lowered_uri or "ssl=true" in lowered_uri
        ):
            # Vercel's Linux runtime benefits from certifi's bundled CAs for Atlas SRV TLS.
            client_kwargs["tlsCAFile"] = certifi.where()

        self.client = MongoClient(mongo_uri, **client_kwargs)
        self.db = self.client[db_name]

        self.users = self.db["users"]
        self.airports = self.db["airports_master"]
        self.airlines = self.db["airlines_master"]
        self.predictions = self.db["flight_predictions"]
        self.alerts = self.db["fare_alerts"]
        self.benchmarks = self.db["model_benchmarks"]
        self.counters = self.db["counters"]

        bootstrap = self.counters.find_one({"_id": "__schema_seeded_v1__"})
        needs_bootstrap = not (
            bootstrap
            and bootstrap.get("seed_airports") == len(seed_airports)
            and bootstrap.get("seed_airlines") == len(seed_airlines)
            and self.users.find_one({}, {"_id": 1}) is not None
        )
        if needs_bootstrap:
            self._ensure_indexes()
            self._seed_initial_data(seed_airports, seed_airlines)
            self.counters.update_one(
                {"_id": "__schema_seeded_v1__"},
                {
                    "$set": {
                        "seed_airports": len(seed_airports),
                        "seed_airlines": len(seed_airlines),
                        "seeded_at": _utc_now(),
                    }
                },
                upsert=True,
            )

    def _next_seq(self, name: str) -> int:
        doc = self.counters.find_one_and_update(
            {"_id": name},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return int(doc["seq"])

    def _ensure_indexes(self) -> None:
        self.users.create_index("id", unique=True)
        self.users.create_index("email", unique=True)
        self.airports.create_index("airport_code", unique=True)
        self.airports.create_index("city_name", unique=True)
        self.airlines.create_index("airline_id", unique=True)
        self.airlines.create_index("airline_name", unique=True)
        self.predictions.create_index("id", unique=True)
        self.predictions.create_index([("source_code", 1), ("dest_code", 1)])
        self.predictions.create_index("user_id")
        self.alerts.create_index("id", unique=True)
        self.alerts.create_index("user_id")
        self.benchmarks.create_index("model_name", unique=True)

    def _seed_initial_data(self, seed_airports: List[tuple], seed_airlines: List[tuple]) -> None:
        for code, city, state in seed_airports:
            self.airports.update_one(
                {"airport_code": code},
                {
                    "$setOnInsert": {
                        "airport_code": code,
                        "city_name": city,
                        "state_name": state,
                        "is_active": True,
                        "created_at": _utc_now(),
                    }
                },
                upsert=True,
            )

        for name, carrier, tier in seed_airlines:
            if not self.airlines.find_one({"airline_name": name}):
                self.airlines.insert_one(
                    {
                        "airline_id": self._next_seq("airlines_master"),
                        "airline_name": name,
                        "carrier_code": carrier,
                        "airline_tier": tier,
                        "is_active": True,
                        "created_at": _utc_now(),
                    }
                )

        demo_users = [
            ("Aarav Traveler", "traveler@farelens.in", "Traveler@123", "traveler"),
            ("Meera Pricing Analyst", "analyst@farelens.in", "Analyst@123", "analyst"),
            ("Lokesh Admin (G1716)", "admin@farelens.in", "Admin@123", "admin"),
        ]
        for full_name, email, pw, role in demo_users:
            if not self.users.find_one({"email": email}):
                self.users.insert_one(
                    {
                        "id": self._next_seq("users"),
                        "full_name": full_name,
                        "email": email,
                        "password_hash": _hash_seed_pw(pw),
                        "role": role,
                        "is_active": True,
                        "created_at": _utc_now(),
                    }
                )

    def _resolve_airport_code(self, city_or_code: str) -> str:
        if city_or_code in self.city_to_iata:
            return self.city_to_iata[city_or_code]
        doc = self.airports.find_one(
            {
                "$or": [
                    {"airport_code": city_or_code.upper()},
                    {"city_name": city_or_code},
                ]
            }
        )
        if doc:
            return doc["airport_code"]
        raise ValueError(f"Unknown airport/city: {city_or_code}")

    def _resolve_airline_doc(self, airline_name: str) -> Dict:
        doc = self.airlines.find_one({"airline_name": airline_name})
        if doc:
            return doc
        new_doc = {
            "airline_id": self._next_seq("airlines_master"),
            "airline_name": airline_name,
            "carrier_code": airline_name[:3].upper(),
            "airline_tier": "Custom",
            "is_active": True,
            "created_at": _utc_now(),
        }
        self.airlines.insert_one(new_doc)
        return new_doc

    def sync_model_benchmarks(self, metrics_payload: Dict) -> None:
        models_dict = metrics_payload.get("models", {})
        sig = hashlib.sha256(
            json.dumps(metrics_payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        marker = self.counters.find_one({"_id": "__benchmarks_sig__"})
        if marker and marker.get("sig") == sig and self.benchmarks.find_one({}, {"_id": 1}) is not None:
            return

        train_samples = int(metrics_payload.get("training_samples", 8369))
        feat_count = int(metrics_payload.get("encoded_feature_count", 167))
        for name, stats in models_dict.items():
            self.benchmarks.update_one(
                {"model_name": name},
                {
                    "$set": {
                        "model_name": name,
                        "r2_score": float(stats["r2_score"]),
                        "mae": float(stats["mae"]),
                        "rmse": float(stats["rmse"]),
                        "cv_r2_mean": stats.get("cv_r2_mean"),
                        "training_samples": train_samples,
                        "feature_count": feat_count,
                        "is_selected": bool(stats.get("is_selected", False)),
                        "evaluated_at": _utc_now(),
                    }
                },
                upsert=True,
            )
        self.counters.update_one(
            {"_id": "__benchmarks_sig__"},
            {"$set": {"sig": sig, "updated_at": _utc_now()}},
            upsert=True,
        )

    @staticmethod
    def _user_to_dict(u: Dict) -> Dict:
        created = u.get("created_at")
        return {
            "id": int(u["id"]),
            "full_name": u["full_name"],
            "email": u["email"],
            "role": u["role"],
            "is_active": bool(u.get("is_active", True)),
            "created_at": created.strftime("%Y-%m-%d %H:%M:%S") if hasattr(created, "strftime") else "",
        }

    def get_user_by_email(self, email: str) -> Optional[SimpleNamespace]:
        doc = self.users.find_one({"email": email.strip().lower()})
        if not doc:
            return None
        return SimpleNamespace(
            id=int(doc["id"]),
            full_name=doc["full_name"],
            email=doc["email"],
            password_hash=doc["password_hash"],
            role=doc["role"],
            is_active=bool(doc.get("is_active", True)),
        )

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        doc = self.users.find_one({"id": int(user_id)})
        return self._user_to_dict(doc) if doc else None

    def create_user(self, full_name: str, email: str, password_hash: str, role: str = "traveler") -> Dict:
        norm_email = email.strip().lower()
        doc = {
            "id": self._next_seq("users"),
            "full_name": full_name.strip(),
            "email": norm_email,
            "password_hash": password_hash,
            "role": role,
            "is_active": True,
            "created_at": _utc_now(),
        }
        try:
            self.users.insert_one(doc)
        except DuplicateKeyError:
            raise ValueError("An account with this email already exists.")
        return self._user_to_dict(doc)

    def list_all_users(self) -> List[Dict]:
        return [self._user_to_dict(u) for u in self.users.find().sort("id", 1)]

    def update_user_admin(
        self, user_id: int, role: Optional[str] = None, is_active: Optional[bool] = None
    ) -> Optional[Dict]:
        updates = {}
        if role is not None:
            updates["role"] = role
        if is_active is not None:
            updates["is_active"] = bool(is_active)
        if not updates:
            return self.get_user_by_id(user_id)
        doc = self.users.find_one_and_update(
            {"id": int(user_id)},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return self._user_to_dict(doc) if doc else None

    def _lookup_maps(self):
        airports_map = {a["airport_code"]: a for a in self.airports.find()}
        airlines_map = {int(a["airline_id"]): a for a in self.airlines.find()}
        users_map = {int(u["id"]): u for u in self.users.find({}, {"id": 1, "email": 1})}
        return airports_map, airlines_map, users_map

    def _prediction_to_dict(self, r: Dict, airports_map: Dict, airlines_map: Dict, users_map: Dict) -> Dict:
        airline_doc = airlines_map.get(int(r["airline_id"]), {})
        src_doc = airports_map.get(r["source_code"], {})
        dst_doc = airports_map.get(r["dest_code"], {})
        user_doc = users_map.get(r["user_id"]) if r.get("user_id") is not None else None
        created = r.get("created_at")
        return {
            "id": int(r["id"]),
            "user_id": r.get("user_id"),
            "airline": airline_doc.get("airline_name", "Unknown"),
            "carrier_code": airline_doc.get("carrier_code", ""),
            "source_code": r["source_code"],
            "dest_code": r["dest_code"],
            "source": src_doc.get("city_name", r["source_code"]),
            "destination": dst_doc.get("city_name", r["dest_code"]),
            "route_str": r["route_str"],
            "additional_info": r["additional_info"],
            "journey_date": r["journey_date"],
            "dep_time": r["dep_time"],
            "arrival_time": r["arrival_time"],
            "duration_mins": int(r["duration_mins"]),
            "total_stops": int(r["total_stops"]),
            "predicted_fare": round(float(r["predicted_fare"]), 2),
            "fare_lower": round(float(r["fare_lower"]), 2),
            "fare_upper": round(float(r["fare_upper"]), 2),
            "fare_category": r["fare_category"],
            "model_name": r["model_name"],
            "model_r2_score": float(r["model_r2_score"]),
            "notes": r.get("notes", ""),
            "user_email": user_doc["email"] if user_doc else "guest",
            "timestamp": created.strftime("%Y-%m-%d %H:%M:%S") if hasattr(created, "strftime") else "",
        }

    def save_prediction_log(
        self,
        airline: str,
        source: str,
        destination: str,
        route_str: str,
        additional_info: str,
        journey_date: str,
        dep_time: str,
        arrival_time: str,
        duration_mins: int,
        total_stops: int,
        predicted_fare: float,
        fare_lower: float,
        fare_upper: float,
        fare_category: str,
        model_name: str,
        model_r2_score: float,
        user_id: Optional[int] = None,
        notes: str = "",
    ) -> int:
        airline_doc = self._resolve_airline_doc(airline)
        src_code = self._resolve_airport_code(source)
        dst_code = self._resolve_airport_code(destination)
        rec_id = self._next_seq("flight_predictions")
        self.predictions.insert_one(
            {
                "id": rec_id,
                "user_id": int(user_id) if user_id is not None else None,
                "airline_id": int(airline_doc["airline_id"]),
                "source_code": src_code,
                "dest_code": dst_code,
                "route_str": route_str,
                "additional_info": additional_info,
                "journey_date": journey_date,
                "dep_time": dep_time,
                "arrival_time": arrival_time,
                "duration_mins": int(duration_mins),
                "total_stops": int(total_stops),
                "predicted_fare": round(float(predicted_fare), 2),
                "fare_lower": round(float(fare_lower), 2),
                "fare_upper": round(float(fare_upper), 2),
                "fare_category": fare_category,
                "model_name": model_name,
                "model_r2_score": round(float(model_r2_score), 4),
                "notes": notes[:255],
                "created_at": _utc_now(),
            }
        )
        return rec_id

    def fetch_recent_predictions(
        self,
        limit: int = 25,
        user_id: Optional[int] = None,
        airline: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict]:
        query: Dict = {}
        if user_id is not None:
            query["user_id"] = int(user_id)
        if airline:
            a_doc = self.airlines.find_one({"airline_name": airline})
            if not a_doc:
                return []
            query["airline_id"] = int(a_doc["airline_id"])
        if search:
            pat = search.strip()
            query["$or"] = [
                {"route_str": {"$regex": pat, "$options": "i"}},
                {"notes": {"$regex": pat, "$options": "i"}},
                {"journey_date": {"$regex": pat, "$options": "i"}},
            ]
        docs = list(self.predictions.find(query).sort("id", DESCENDING).limit(int(limit)))
        airports_map, airlines_map, users_map = self._lookup_maps()
        return [self._prediction_to_dict(d, airports_map, airlines_map, users_map) for d in docs]

    def update_prediction_notes(
        self,
        prediction_id: int,
        notes: str,
        requester_id: int,
        requester_role: str,
    ) -> Optional[Dict]:
        rec = self.predictions.find_one({"id": int(prediction_id)})
        if not rec:
            return None
        if requester_role not in ("admin", "analyst") and rec.get("user_id") not in (None, requester_id):
            raise PermissionError("You can only edit your own prediction logs.")
        updated = self.predictions.find_one_and_update(
            {"id": int(prediction_id)},
            {"$set": {"notes": notes.strip()[:255]}},
            return_document=ReturnDocument.AFTER,
        )
        airports_map, airlines_map, users_map = self._lookup_maps()
        return self._prediction_to_dict(updated, airports_map, airlines_map, users_map)

    def delete_prediction_record(
        self, prediction_id: int, requester_id: int, requester_role: str
    ) -> bool:
        rec = self.predictions.find_one({"id": int(prediction_id)})
        if not rec:
            return False
        if requester_role != "admin" and rec.get("user_id") not in (None, requester_id):
            raise PermissionError("You can only delete your own prediction logs.")
        self.predictions.delete_one({"id": int(prediction_id)})
        return True

    def _alert_to_dict(self, a: Dict, airports_map: Dict, airlines_map: Dict) -> Dict:
        airline_doc = airlines_map.get(int(a["airline_id"]), {})
        src_doc = airports_map.get(a["source_code"], {})
        dst_doc = airports_map.get(a["dest_code"], {})
        created = a.get("created_at")
        return {
            "id": int(a["id"]),
            "user_id": int(a["user_id"]),
            "prediction_id": a.get("prediction_id"),
            "airline": airline_doc.get("airline_name", "Unknown"),
            "source_code": a["source_code"],
            "dest_code": a["dest_code"],
            "source": src_doc.get("city_name", a["source_code"]),
            "destination": dst_doc.get("city_name", a["dest_code"]),
            "journey_date": a["journey_date"],
            "target_price": round(float(a["target_price"]), 2),
            "estimated_price": round(float(a["estimated_price"]), 2),
            "status": a["status"],
            "notes": a.get("notes", ""),
            "created_at": created.strftime("%Y-%m-%d %H:%M:%S") if hasattr(created, "strftime") else "",
        }

    def create_fare_alert(
        self,
        user_id: int,
        airline: str,
        source: str,
        destination: str,
        journey_date: str,
        target_price: float,
        estimated_price: float,
        prediction_id: Optional[int] = None,
        notes: str = "",
    ) -> Dict:
        airline_doc = self._resolve_airline_doc(airline)
        src_code = self._resolve_airport_code(source)
        dst_code = self._resolve_airport_code(destination)
        status_val = "target_met" if estimated_price <= target_price else "watching"
        doc = {
            "id": self._next_seq("fare_alerts"),
            "user_id": int(user_id),
            "prediction_id": int(prediction_id) if prediction_id is not None else None,
            "airline_id": int(airline_doc["airline_id"]),
            "source_code": src_code,
            "dest_code": dst_code,
            "journey_date": journey_date,
            "target_price": round(float(target_price), 2),
            "estimated_price": round(float(estimated_price), 2),
            "status": status_val,
            "notes": notes.strip()[:255],
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }
        self.alerts.insert_one(doc)
        airports_map, airlines_map, _ = self._lookup_maps()
        return self._alert_to_dict(doc, airports_map, airlines_map)

    def fetch_fare_alerts(self, user_id: Optional[int] = None, is_admin: bool = False) -> List[Dict]:
        query = {} if (is_admin or user_id is None) else {"user_id": int(user_id)}
        docs = list(self.alerts.find(query).sort("id", DESCENDING))
        airports_map, airlines_map, _ = self._lookup_maps()
        return [self._alert_to_dict(d, airports_map, airlines_map) for d in docs]

    def update_fare_alert(
        self,
        alert_id: int,
        user_id: int,
        is_admin: bool,
        target_price: Optional[float] = None,
        status_val: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[Dict]:
        alert = self.alerts.find_one({"id": int(alert_id)})
        if not alert:
            return None
        if not is_admin and int(alert["user_id"]) != int(user_id):
            raise PermissionError("You can only modify your own fare alerts.")
        updates: Dict = {"updated_at": _utc_now()}
        current_status = alert["status"]
        if target_price is not None:
            tp = round(float(target_price), 2)
            updates["target_price"] = tp
            if status_val is None and current_status != "paused":
                updates["status"] = "target_met" if float(alert["estimated_price"]) <= tp else "watching"
        if status_val is not None:
            updates["status"] = status_val
        if notes is not None:
            updates["notes"] = notes.strip()[:255]

        updated = self.alerts.find_one_and_update(
            {"id": int(alert_id)},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        airports_map, airlines_map, _ = self._lookup_maps()
        return self._alert_to_dict(updated, airports_map, airlines_map)

    def delete_fare_alert(self, alert_id: int, user_id: int, is_admin: bool) -> bool:
        alert = self.alerts.find_one({"id": int(alert_id)})
        if not alert:
            return False
        if not is_admin and int(alert["user_id"]) != int(user_id):
            raise PermissionError("You can only delete your own fare alerts.")
        self.alerts.delete_one({"id": int(alert_id)})
        return True

    def get_master_catalog(self) -> Dict:
        airports = list(self.airports.find().sort("airport_code", 1))
        airlines = list(self.airlines.find().sort("airline_name", 1))
        benchmarks = list(self.benchmarks.find().sort("r2_score", DESCENDING))
        return {
            "airports": [
                {
                    "airport_code": a["airport_code"],
                    "city_name": a["city_name"],
                    "state_name": a["state_name"],
                    "is_active": bool(a.get("is_active", True)),
                }
                for a in airports
            ],
            "airlines": [
                {
                    "airline_id": int(al["airline_id"]),
                    "airline_name": al["airline_name"],
                    "carrier_code": al["carrier_code"],
                    "airline_tier": al["airline_tier"],
                    "is_active": bool(al.get("is_active", True)),
                }
                for al in airlines
            ],
            "benchmarks": [
                {
                    "model_name": b["model_name"],
                    "r2_score": float(b["r2_score"]),
                    "mae": float(b["mae"]),
                    "rmse": float(b["rmse"]),
                    "cv_r2_mean": b.get("cv_r2_mean"),
                    "is_selected": bool(b.get("is_selected", False)),
                }
                for b in benchmarks
            ],
        }

    def add_airline_catalog(self, airline_name: str, carrier_code: str, airline_tier: str) -> Dict:
        name = airline_name.strip()
        if self.airlines.find_one({"airline_name": name}):
            raise ValueError("Airline already exists in catalog.")
        doc = {
            "airline_id": self._next_seq("airlines_master"),
            "airline_name": name,
            "carrier_code": carrier_code.strip().upper(),
            "airline_tier": airline_tier.strip(),
            "is_active": True,
            "created_at": _utc_now(),
        }
        self.airlines.insert_one(doc)
        return {
            "airline_id": int(doc["airline_id"]),
            "airline_name": doc["airline_name"],
            "carrier_code": doc["carrier_code"],
            "airline_tier": doc["airline_tier"],
            "is_active": True,
        }

    def get_database_status(self) -> Dict:
        is_atlas = "mongodb+srv://" in self.mongo_uri
        return {
            "status": "online",
            "db_type": "MongoDB Atlas (Cloud Live)" if is_atlas else "MongoDB (Local/Docker Live)",
            "normalization": f"MongoDB Normalized References ({self.db_name} • 6 Collections)",
            "table_counts": {
                "users": self.users.count_documents({}),
                "airports_master": self.airports.count_documents({}),
                "airlines_master": self.airlines.count_documents({}),
                "flight_predictions": self.predictions.count_documents({}),
                "fare_alerts": self.alerts.count_documents({}),
                "model_benchmarks": self.benchmarks.count_documents({}),
            },
            "mysql_configured_uri": self.db_name,
        }
