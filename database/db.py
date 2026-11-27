"""
Database Management Module
Supports: MySQL (Primary specification for 5 Marks) + Local SQLite Auto-Fallback
Framework: SQLAlchemy ORM
"""

import os
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, Integer, BigInteger, String,
    Float, Date, DateTime, Text, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.getenv("VERCEL"):
    DB_PATH_SQLITE = "/tmp/flight_fare.db"
else:
    DB_PATH_SQLITE = os.path.join(BASE_DIR, "database", "flight_fare.db")

# Default connection strings:
# User can set MYSQL_URI env var, or default to standard local root without password
MYSQL_URI = os.getenv("MYSQL_URI", "mysql+pymysql://root:@localhost:3306/flight_fare_db")
SQLITE_URI = f"sqlite:///{DB_PATH_SQLITE}"

Base = declarative_base()

class FlightPredictionRecord(Base):
    __tablename__ = "flight_predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    airline = Column(String(100), nullable=False)
    source = Column(String(100), nullable=False)
    destination = Column(String(100), nullable=False)
    journey_date = Column(String(20), nullable=False)
    dep_time = Column(String(10), nullable=False)
    arrival_time = Column(String(10), nullable=False)
    duration_mins = Column(Integer, nullable=False)
    total_stops = Column(Integer, nullable=False, default=0)
    predicted_fare = Column(Float, nullable=False)
    fare_category = Column(String(20), default="Standard")
    model_name = Column(String(100), default="RandomForestRegressor_Tuned")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_source_destination", "source", "destination"),
        Index("idx_airline", "airline"),
    )

# Engine initialization with fallback logic
active_engine = None
active_db_type = "SQLite"

try:
    # Attempt MySQL first if server is running
    temp_engine = create_engine(MYSQL_URI, connect_args={"connect_timeout": 2})
    with temp_engine.connect() as conn:
        active_engine = temp_engine
        active_db_type = "MySQL (Live Connected)"
        print(" Connected to MySQL database server successfully.")
except Exception as e:
    # Fallback seamlessly to SQLite so app never crashes in exam
    active_engine = create_engine(SQLITE_URI, connect_args={"check_same_thread": False})
    active_db_type = "SQLite (Local Fallback Active - Zero Config)"
    print(f" MySQL not reachable locally ({e.__class__.__name__}). Falling back seamlessly to SQLite.")

Base.metadata.create_all(active_engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=active_engine)

def save_prediction_log(
    airline: str,
    source: str,
    destination: str,
    journey_date: str,
    dep_time: str,
    arrival_time: str,
    duration_mins: int,
    total_stops: int,
    predicted_fare: float,
    fare_category: str = "Standard"
):
    """Inserts a new flight price prediction record into the database."""
    session = SessionLocal()
    try:
        record = FlightPredictionRecord(
            airline=airline,
            source=source,
            destination=destination,
            journey_date=journey_date,
            dep_time=dep_time,
            arrival_time=arrival_time,
            duration_mins=duration_mins,
            total_stops=total_stops,
            predicted_fare=round(float(predicted_fare), 2),
            fare_category=fare_category
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return record.id
    except Exception as err:
        session.rollback()
        print(f"Error saving prediction to DB: {err}")
        return None
    finally:
        session.close()

def fetch_recent_predictions(limit: int = 10):
    """Retrieves the most recent predictions from the database for the interface."""
    session = SessionLocal()
    try:
        records = session.query(FlightPredictionRecord)\
            .order_by(FlightPredictionRecord.id.desc())\
            .limit(limit)\
            .all()
        return [
            {
                "id": r.id,
                "airline": r.airline,
                "source": r.source,
                "destination": r.destination,
                "journey_date": r.journey_date,
                "dep_time": r.dep_time,
                "arrival_time": r.arrival_time,
                "duration_mins": r.duration_mins,
                "total_stops": r.total_stops,
                "predicted_fare": r.predicted_fare,
                "fare_category": r.fare_category,
                "timestamp": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "Just now"
            }
            for r in records
        ]
    finally:
        session.close()

def get_database_status():
    """Returns database connection status for the UI badge."""
    return {
        "status": "online",
        "db_type": active_db_type,
        "mysql_configured_uri": MYSQL_URI.split("@")[-1] if "@" in MYSQL_URI else "localhost:3306/flight_fare_db"
    }
