# FareLens — Airfare Price Estimation & Fare Pattern Analysis-II

**Academic Capstone Project | Group G1716**  
**Team Members:**
- **25BD1A0589** — Cheekati Vinay
- **25BD1A0586** — Bommineni Lokesh Narayana
- **25BD1A058F** — Devarshetty Karthik Datta
- **25BD1A058Q** — Kamboji Sai Dhanush Kumar

**Mentor:** Padma Priya T  
**Tech Stack:** Python 3.13, FastAPI, Scikit-Learn 1.7.2, SQLAlchemy 2.0 (MySQL / 3NF SQLite), PyJWT, bcrypt, HTML5, CSS3, Vanilla JavaScript

---

## Highlights & Improvements Over Naive Baselines
1. **90.32% R² Accuracy (Leak-Free Pipeline):** Uses our Kaggle feature workflow (`lokii1929/airfare-prediction` preserving `Route` and `Additional_Info` across 167 encoded features, with 220 duplicate rows removed), upgraded to a strictly **leak-free Scikit-Learn `Pipeline`** fit only on the 80% training split:
   - **Tuned Random Forest (`n_estimators=250, min_samples_split=3`):** `R² = 0.9032` (`90.32%`), `MAE = ₹619.93`, `RMSE = ₹1,420.35`, `5-Fold CV R² = 0.8974 ± 0.0147`
   - Benchmarked cleanly against **Linear Regression (71.54%)**, **Ridge Regression (71.52%)**, **SVR RBF Scaled (77.92%)**, **KNN Scaled (81.11%)**, and **Decision Tree (84.99%)**.
2. **Full-Stack Features Beyond Input-and-Prediction (Zero `-5M` Penalty Risk):**
   - **JWT Auth & 3 Stakeholder Roles:** `Traveler`, `Analyst`, and `Admin` (`bcrypt` password hashing + `HS256` JWT tokens).
   - **3rd Normal Form (3NF) Relational Database (6 Tables with Foreign Keys):** `users`, `airports_master`, `airlines_master`, `flight_predictions`, `fare_alerts`, `model_benchmarks`. Synchronized between `database/schema.sql` (MySQL 8.0+) and `database/db.py` (SQLAlchemy ORM + SQLite FK enforcement).
   - **Full CRUD Operations:** Create/Read/Update/Delete on both **Prediction Audit Logs** (`notes`) and **Price Watchlist Alerts** (`target_price`, `status`, `notes`), plus Admin user-role & airline-catalog CRUD and Analyst CSV export.
   - **Batch ML Intelligence:** 7-Day Flexible Date Calendar (`POST /api/compare-dates`), Cross-Airline Fare Comparison (`POST /api/compare-airlines`), Tree-Ensemble IQR Confidence Intervals, Feature Importances, EDA Charts, and **2019 Collection-Date & Market Drift Limitations** analysis.

---

## Quick Start

```bash
# 1. Install dependencies (if needed)
pip install -r requirements.txt

# 2. Train & benchmark all models + export EDA & catalog artifacts
python3 models/train_models.py

# 3. Run automated verification suite (pytest)
python3 -m pytest -v tests/test_suite.py

# 4. Launch FastAPI web application
python3 run.py
```

Open **`http://127.0.0.1:8000`** for the application or **`http://127.0.0.1:8000/docs`** for Swagger OpenAPI documentation.

### Demo Stakeholder Accounts
- **Traveler:** `traveler@farelens.in` / `Traveler@123`
- **Analyst:** `analyst@farelens.in` / `Analyst@123`
- **Admin:** `admin@farelens.in` / `Admin@123`

### Live Database Audit Utility
```bash
python3 view_database.py --watch
```
