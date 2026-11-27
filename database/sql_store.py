"""Normalized 3NF Relational Database Store (SQLAlchemy ORM: MySQL + SQLite)."""

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import bcrypt
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    create_engine,
    event,
    func,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_seed_pw(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(150), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="traveler")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=_utc_now)

    predictions = relationship("FlightPredictionRecord", back_populates="user")
    alerts = relationship("FareAlert", back_populates="user", cascade="all, delete-orphan")


class AirportMaster(Base):
    __tablename__ = "airports_master"

    airport_code = Column(String(10), primary_key=True)
    city_name = Column(String(100), nullable=False, unique=True)
    state_name = Column(String(100), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=_utc_now)


class AirlineMaster(Base):
    __tablename__ = "airlines_master"

    airline_id = Column(Integer, primary_key=True, autoincrement=True)
    airline_name = Column(String(100), nullable=False, unique=True)
    carrier_code = Column(String(16), nullable=False)
    airline_tier = Column(String(40), nullable=False, default="Full-Service")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=_utc_now)

    predictions = relationship("FlightPredictionRecord", back_populates="airline_rel")


class FlightPredictionRecord(Base):
    __tablename__ = "flight_predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    airline_id = Column(Integer, ForeignKey("airlines_master.airline_id"), nullable=False)
    source_code = Column(String(10), ForeignKey("airports_master.airport_code"), nullable=False)
    dest_code = Column(String(10), ForeignKey("airports_master.airport_code"), nullable=False)
    route_str = Column(String(150), nullable=False)
    additional_info = Column(String(100), nullable=False, default="No info")
    journey_date = Column(String(20), nullable=False)
    dep_time = Column(String(10), nullable=False)
    arrival_time = Column(String(10), nullable=False)
    duration_mins = Column(Integer, nullable=False)
    total_stops = Column(Integer, nullable=False, default=0)
    predicted_fare = Column(Float, nullable=False)
    fare_lower = Column(Float, nullable=False)
    fare_upper = Column(Float, nullable=False)
    fare_category = Column(String(20), nullable=False, default="Standard")
    model_name = Column(String(100), nullable=False, default="Random Forest (Tuned Final)")
    model_r2_score = Column(Float, nullable=False, default=0.9032)
    notes = Column(String(255), nullable=False, default="")
    created_at = Column(DateTime, default=_utc_now)

    user = relationship("User", back_populates="predictions")
    airline_rel = relationship("AirlineMaster", back_populates="predictions")
    source_airport = relationship("AirportMaster", foreign_keys=[source_code])
    dest_airport = relationship("AirportMaster", foreign_keys=[dest_code])

    __table_args__ = (
        CheckConstraint("total_stops >= 0 AND total_stops <= 4", name="chk_stops_range"),
        CheckConstraint("duration_mins > 0", name="chk_duration_pos"),
        CheckConstraint("predicted_fare > 0", name="chk_fare_pos"),
        Index("idx_pred_route", "source_code", "dest_code"),
        Index("idx_pred_user", "user_id"),
        Index("idx_pred_airline", "airline_id"),
    )


class FareAlert(Base):
    __tablename__ = "fare_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    prediction_id = Column(Integer, ForeignKey("flight_predictions.id", ondelete="SET NULL"), nullable=True)
    airline_id = Column(Integer, ForeignKey("airlines_master.airline_id"), nullable=False)
    source_code = Column(String(10), ForeignKey("airports_master.airport_code"), nullable=False)
    dest_code = Column(String(10), ForeignKey("airports_master.airport_code"), nullable=False)
    journey_date = Column(String(20), nullable=False)
    target_price = Column(Float, nullable=False)
    estimated_price = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, default="watching")
    notes = Column(String(255), nullable=False, default="")
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    user = relationship("User", back_populates="alerts")
    airline_rel = relationship("AirlineMaster")
    source_airport = relationship("AirportMaster", foreign_keys=[source_code])
    dest_airport = relationship("AirportMaster", foreign_keys=[dest_code])

    __table_args__ = (CheckConstraint("target_price > 0", name="chk_target_pos"),)


class ModelBenchmark(Base):
    __tablename__ = "model_benchmarks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(100), nullable=False, unique=True)
    r2_score = Column(Float, nullable=False)
    mae = Column(Float, nullable=False)
    rmse = Column(Float, nullable=False)
    cv_r2_mean = Column(Float, nullable=True)
    training_samples = Column(Integer, nullable=False)
    feature_count = Column(Integer, nullable=False)
    is_selected = Column(Boolean, nullable=False, default=False)
    evaluated_at = Column(DateTime, default=_utc_now)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class SQLStore:
    def __init__(
        self,
        mysql_uri: str,
        sqlite_path: str,
        city_to_iata: Dict[str, str],
        seed_airports: List[tuple],
        seed_airlines: List[tuple],
    ):
        self.mysql_uri = mysql_uri
        self.city_to_iata = city_to_iata
        os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
        sqlite_uri = f"sqlite:///{sqlite_path}"

        try:
            temp_engine = create_engine(mysql_uri, connect_args={"connect_timeout": 2})
            with temp_engine.connect():
                self.engine = temp_engine
                self.db_type = "MySQL (Live Connected)"
        except Exception:
            self.engine = create_engine(sqlite_uri, connect_args={"check_same_thread": False})
            self.db_type = "SQLite (3NF Local Engine)"

        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self._init_seed_data(seed_airports, seed_airlines)

    def _init_seed_data(self, seed_airports: List[tuple], seed_airlines: List[tuple]) -> None:
        session = self.SessionLocal()
        try:
            for code, city, state in seed_airports:
                if not session.query(AirportMaster).filter_by(airport_code=code).first():
                    session.add(AirportMaster(airport_code=code, city_name=city, state_name=state))

            for name, carrier, tier in seed_airlines:
                if not session.query(AirlineMaster).filter_by(airline_name=name).first():
                    session.add(AirlineMaster(airline_name=name, carrier_code=carrier, airline_tier=tier))

            demo_users = [
                ("Aarav Traveler", "traveler@farelens.in", "Traveler@123", "traveler"),
                ("Meera Pricing Analyst", "analyst@farelens.in", "Analyst@123", "analyst"),
                ("Lokesh Admin (G1716)", "admin@farelens.in", "Admin@123", "admin"),
            ]
            for full_name, email, pw, role in demo_users:
                if not session.query(User).filter_by(email=email).first():
                    session.add(
                        User(
                            full_name=full_name,
                            email=email,
                            password_hash=_hash_seed_pw(pw),
                            role=role,
                        )
                    )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _resolve_airport_code(self, session, city_or_code: str) -> str:
        if city_or_code in self.city_to_iata:
            return self.city_to_iata[city_or_code]
        airport = (
            session.query(AirportMaster)
            .filter(
                (AirportMaster.airport_code == city_or_code.upper())
                | (AirportMaster.city_name == city_or_code)
            )
            .first()
        )
        if airport:
            return airport.airport_code
        raise ValueError(f"Unknown airport/city: {city_or_code}")

    def _resolve_airline_id(self, session, airline_name: str) -> int:
        airline = session.query(AirlineMaster).filter_by(airline_name=airline_name).first()
        if airline:
            return airline.airline_id
        new_airline = AirlineMaster(
            airline_name=airline_name,
            carrier_code=airline_name[:3].upper(),
            airline_tier="Custom",
        )
        session.add(new_airline)
        session.flush()
        return new_airline.airline_id

    @staticmethod
    def _user_to_dict(u: User) -> Dict:
        return {
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "role": u.role,
            "is_active": bool(u.is_active),
            "created_at": u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else "",
        }

    def sync_model_benchmarks(self, metrics_payload: Dict) -> None:
        models_dict = metrics_payload.get("models", {})
        train_samples = int(metrics_payload.get("training_samples", 8369))
        feat_count = int(metrics_payload.get("encoded_feature_count", 167))
        session = self.SessionLocal()
        try:
            for name, stats in models_dict.items():
                row = session.query(ModelBenchmark).filter_by(model_name=name).first()
                if row:
                    row.r2_score = float(stats["r2_score"])
                    row.mae = float(stats["mae"])
                    row.rmse = float(stats["rmse"])
                    row.cv_r2_mean = stats.get("cv_r2_mean")
                    row.training_samples = train_samples
                    row.feature_count = feat_count
                    row.is_selected = bool(stats.get("is_selected", False))
                else:
                    session.add(
                        ModelBenchmark(
                            model_name=name,
                            r2_score=float(stats["r2_score"]),
                            mae=float(stats["mae"]),
                            rmse=float(stats["rmse"]),
                            cv_r2_mean=stats.get("cv_r2_mean"),
                            training_samples=train_samples,
                            feature_count=feat_count,
                            is_selected=bool(stats.get("is_selected", False)),
                        )
                    )
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    def get_user_by_email(self, email: str) -> Optional[User]:
        session = self.SessionLocal()
        try:
            return session.query(User).filter_by(email=email.strip().lower()).first()
        finally:
            session.close()

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        session = self.SessionLocal()
        try:
            u = session.query(User).filter_by(id=user_id).first()
            return self._user_to_dict(u) if u else None
        finally:
            session.close()

    def create_user(self, full_name: str, email: str, password_hash: str, role: str = "traveler") -> Dict:
        session = self.SessionLocal()
        try:
            norm_email = email.strip().lower()
            if session.query(User).filter_by(email=norm_email).first():
                raise ValueError("An account with this email already exists.")
            user = User(
                full_name=full_name.strip(),
                email=norm_email,
                password_hash=password_hash,
                role=role,
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return self._user_to_dict(user)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_all_users(self) -> List[Dict]:
        session = self.SessionLocal()
        try:
            users = session.query(User).order_by(User.id.asc()).all()
            return [self._user_to_dict(u) for u in users]
        finally:
            session.close()

    def update_user_admin(
        self, user_id: int, role: Optional[str] = None, is_active: Optional[bool] = None
    ) -> Optional[Dict]:
        session = self.SessionLocal()
        try:
            user = session.query(User).filter_by(id=user_id).first()
            if not user:
                return None
            if role is not None:
                user.role = role
            if is_active is not None:
                user.is_active = bool(is_active)
            session.commit()
            session.refresh(user)
            return self._user_to_dict(user)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _prediction_to_dict(r: FlightPredictionRecord) -> Dict:
        return {
            "id": r.id,
            "user_id": r.user_id,
            "airline": r.airline_rel.airline_name if r.airline_rel else "Unknown",
            "carrier_code": r.airline_rel.carrier_code if r.airline_rel else "",
            "source_code": r.source_code,
            "dest_code": r.dest_code,
            "source": r.source_airport.city_name if r.source_airport else r.source_code,
            "destination": r.dest_airport.city_name if r.dest_airport else r.dest_code,
            "route_str": r.route_str,
            "additional_info": r.additional_info,
            "journey_date": r.journey_date,
            "dep_time": r.dep_time,
            "arrival_time": r.arrival_time,
            "duration_mins": r.duration_mins,
            "total_stops": r.total_stops,
            "predicted_fare": round(float(r.predicted_fare), 2),
            "fare_lower": round(float(r.fare_lower), 2),
            "fare_upper": round(float(r.fare_upper), 2),
            "fare_category": r.fare_category,
            "model_name": r.model_name,
            "model_r2_score": r.model_r2_score,
            "notes": r.notes or "",
            "user_email": r.user.email if r.user else "guest",
            "timestamp": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
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
        session = self.SessionLocal()
        try:
            airline_id = self._resolve_airline_id(session, airline)
            src_code = self._resolve_airport_code(session, source)
            dst_code = self._resolve_airport_code(session, destination)
            record = FlightPredictionRecord(
                user_id=user_id,
                airline_id=airline_id,
                source_code=src_code,
                dest_code=dst_code,
                route_str=route_str,
                additional_info=additional_info,
                journey_date=journey_date,
                dep_time=dep_time,
                arrival_time=arrival_time,
                duration_mins=int(duration_mins),
                total_stops=int(total_stops),
                predicted_fare=round(float(predicted_fare), 2),
                fare_lower=round(float(fare_lower), 2),
                fare_upper=round(float(fare_upper), 2),
                fare_category=fare_category,
                model_name=model_name,
                model_r2_score=round(float(model_r2_score), 4),
                notes=notes[:255],
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record.id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def fetch_recent_predictions(
        self,
        limit: int = 25,
        user_id: Optional[int] = None,
        airline: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict]:
        session = self.SessionLocal()
        try:
            q = session.query(FlightPredictionRecord)
            if user_id is not None:
                q = q.filter(FlightPredictionRecord.user_id == user_id)
            if airline:
                q = q.join(AirlineMaster).filter(AirlineMaster.airline_name == airline)
            if search:
                pat = f"%{search.strip()}%"
                q = q.filter(
                    (FlightPredictionRecord.route_str.ilike(pat))
                    | (FlightPredictionRecord.notes.ilike(pat))
                    | (FlightPredictionRecord.journey_date.ilike(pat))
                )
            records = q.order_by(FlightPredictionRecord.id.desc()).limit(limit).all()
            return [self._prediction_to_dict(r) for r in records]
        finally:
            session.close()

    def update_prediction_notes(
        self,
        prediction_id: int,
        notes: str,
        requester_id: int,
        requester_role: str,
    ) -> Optional[Dict]:
        session = self.SessionLocal()
        try:
            rec = session.query(FlightPredictionRecord).filter_by(id=prediction_id).first()
            if not rec:
                return None
            if requester_role not in ("admin", "analyst") and rec.user_id not in (None, requester_id):
                raise PermissionError("You can only edit your own prediction logs.")
            rec.notes = notes.strip()[:255]
            session.commit()
            session.refresh(rec)
            return self._prediction_to_dict(rec)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_prediction_record(
        self, prediction_id: int, requester_id: int, requester_role: str
    ) -> bool:
        session = self.SessionLocal()
        try:
            rec = session.query(FlightPredictionRecord).filter_by(id=prediction_id).first()
            if not rec:
                return False
            if requester_role != "admin" and rec.user_id not in (None, requester_id):
                raise PermissionError("You can only delete your own prediction logs.")
            session.delete(rec)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _alert_to_dict(a: FareAlert) -> Dict:
        return {
            "id": a.id,
            "user_id": a.user_id,
            "prediction_id": a.prediction_id,
            "airline": a.airline_rel.airline_name if a.airline_rel else "Unknown",
            "source_code": a.source_code,
            "dest_code": a.dest_code,
            "source": a.source_airport.city_name if a.source_airport else a.source_code,
            "destination": a.dest_airport.city_name if a.dest_airport else a.dest_code,
            "journey_date": a.journey_date,
            "target_price": round(float(a.target_price), 2),
            "estimated_price": round(float(a.estimated_price), 2),
            "status": a.status,
            "notes": a.notes or "",
            "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else "",
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
        session = self.SessionLocal()
        try:
            airline_id = self._resolve_airline_id(session, airline)
            src_code = self._resolve_airport_code(session, source)
            dst_code = self._resolve_airport_code(session, destination)
            status_val = "target_met" if estimated_price <= target_price else "watching"
            alert = FareAlert(
                user_id=user_id,
                prediction_id=prediction_id,
                airline_id=airline_id,
                source_code=src_code,
                dest_code=dst_code,
                journey_date=journey_date,
                target_price=round(float(target_price), 2),
                estimated_price=round(float(estimated_price), 2),
                status=status_val,
                notes=notes.strip()[:255],
            )
            session.add(alert)
            session.commit()
            session.refresh(alert)
            return self._alert_to_dict(alert)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def fetch_fare_alerts(self, user_id: Optional[int] = None, is_admin: bool = False) -> List[Dict]:
        session = self.SessionLocal()
        try:
            q = session.query(FareAlert)
            if not is_admin and user_id is not None:
                q = q.filter(FareAlert.user_id == user_id)
            rows = q.order_by(FareAlert.id.desc()).all()
            return [self._alert_to_dict(r) for r in rows]
        finally:
            session.close()

    def update_fare_alert(
        self,
        alert_id: int,
        user_id: int,
        is_admin: bool,
        target_price: Optional[float] = None,
        status_val: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[Dict]:
        session = self.SessionLocal()
        try:
            alert = session.query(FareAlert).filter_by(id=alert_id).first()
            if not alert:
                return None
            if not is_admin and alert.user_id != user_id:
                raise PermissionError("You can only modify your own fare alerts.")
            if target_price is not None:
                alert.target_price = round(float(target_price), 2)
                if alert.status != "paused":
                    alert.status = "target_met" if alert.estimated_price <= alert.target_price else "watching"
            if status_val is not None:
                alert.status = status_val
            if notes is not None:
                alert.notes = notes.strip()[:255]
            session.commit()
            session.refresh(alert)
            return self._alert_to_dict(alert)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_fare_alert(self, alert_id: int, user_id: int, is_admin: bool) -> bool:
        session = self.SessionLocal()
        try:
            alert = session.query(FareAlert).filter_by(id=alert_id).first()
            if not alert:
                return False
            if not is_admin and alert.user_id != user_id:
                raise PermissionError("You can only delete your own fare alerts.")
            session.delete(alert)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_master_catalog(self) -> Dict:
        session = self.SessionLocal()
        try:
            airports = session.query(AirportMaster).order_by(AirportMaster.airport_code).all()
            airlines = session.query(AirlineMaster).order_by(AirlineMaster.airline_name).all()
            benchmarks = session.query(ModelBenchmark).order_by(ModelBenchmark.r2_score.desc()).all()
            return {
                "airports": [
                    {
                        "airport_code": a.airport_code,
                        "city_name": a.city_name,
                        "state_name": a.state_name,
                        "is_active": bool(a.is_active),
                    }
                    for a in airports
                ],
                "airlines": [
                    {
                        "airline_id": al.airline_id,
                        "airline_name": al.airline_name,
                        "carrier_code": al.carrier_code,
                        "airline_tier": al.airline_tier,
                        "is_active": bool(al.is_active),
                    }
                    for al in airlines
                ],
                "benchmarks": [
                    {
                        "model_name": b.model_name,
                        "r2_score": b.r2_score,
                        "mae": b.mae,
                        "rmse": b.rmse,
                        "cv_r2_mean": b.cv_r2_mean,
                        "is_selected": bool(b.is_selected),
                    }
                    for b in benchmarks
                ],
            }
        finally:
            session.close()

    def add_airline_catalog(self, airline_name: str, carrier_code: str, airline_tier: str) -> Dict:
        session = self.SessionLocal()
        try:
            if session.query(AirlineMaster).filter_by(airline_name=airline_name.strip()).first():
                raise ValueError("Airline already exists in catalog.")
            item = AirlineMaster(
                airline_name=airline_name.strip(),
                carrier_code=carrier_code.strip().upper(),
                airline_tier=airline_tier.strip(),
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return {
                "airline_id": item.airline_id,
                "airline_name": item.airline_name,
                "carrier_code": item.carrier_code,
                "airline_tier": item.airline_tier,
                "is_active": bool(item.is_active),
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_database_status(self) -> Dict:
        session = self.SessionLocal()
        try:
            counts = {
                "users": session.query(func.count(User.id)).scalar() or 0,
                "airports_master": session.query(func.count(AirportMaster.airport_code)).scalar() or 0,
                "airlines_master": session.query(func.count(AirlineMaster.airline_id)).scalar() or 0,
                "flight_predictions": session.query(func.count(FlightPredictionRecord.id)).scalar() or 0,
                "fare_alerts": session.query(func.count(FareAlert.id)).scalar() or 0,
                "model_benchmarks": session.query(func.count(ModelBenchmark.id)).scalar() or 0,
            }
            return {
                "status": "online",
                "db_type": self.db_type,
                "normalization": "3NF (Third Normal Form) with Enforced Foreign Keys",
                "table_counts": counts,
                "mysql_configured_uri": self.mysql_uri.split("@")[-1]
                if "@" in self.mysql_uri
                else "localhost:3306/flight_fare_db",
            }
        finally:
            session.close()
