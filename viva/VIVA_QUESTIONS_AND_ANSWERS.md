# Viva Defense Guide & Complete Technical Reference

**Project Title:** Airfare Price Estimation and Fare Pattern Analysis-II (`FareLens`)  
**Team (Group G1716):** Cheekati Vinay, Bommineni Lokesh Narayana, Devarshetty Karthik Datta, Kamboji Sai Dhanush Kumar  
**Mentor:** Padma Priya T

---

## 1. Evaluation Rubric Alignment (40 Marks Checklist)

| Rubric Area | Marks | How FareLens Satisfies Every Criterion |
|---|---|---|
| **A. Presentation** | 5 | Clear problem statement, architecture diagram, 16-step flow, market-drift analysis, and interactive Viva modal inside the UI. |
| **B. Code Execution** | 20 | Modular Python (`models/`, `database/`, `backend/`, `frontend/`, `tests/`), zero-leakage `Pipeline`, Pydantic `422` validation, `pytest` suite covering ML, auth, RBAC, and CRUD. |
| **C. Database Design** | 5 | True **3NF schema** across 6 tables (`users`, `airports_master`, `airlines_master`, `flight_predictions`, `fare_alerts`, `model_benchmarks`) with Foreign Keys, Check Constraints, Indexes, and full **Create / Read / Update / Delete** in both MySQL (`schema.sql`) and SQLAlchemy (`db.py`). |
| **D. Stakeholder Usage** | 5 | Real registration & login (`bcrypt` + PyJWT `HS256`), 3 roles (`Traveler`, `Analyst`, `Admin`), role-enforced UI & API guards (`401`/`403`), accessible dashboard. |
| **E. Innovation** | 5 | Preserves `Route` + `Additional_Info` for **90.32% R²**, tree-ensemble IQR confidence bands, 7-day flexible date finder, 8-airline batch comparison, and 2019 collection-date drift calibration. |

---

## 2. ML Algorithm Benchmark Results (Held-Out Validation: 2,093 Rows)

All models were trained strictly on the **8,369 training rows** (`10,683` raw → `1` null dropped → `220` duplicates dropped → `10,462` clean rows) using a leak-free Scikit-Learn `Pipeline`:

| Algorithm | R² Score | MAE (INR) | RMSE (INR) | Key Observation |
|---|---|---|---|---|
| **Linear Regression** | 71.54% | ₹1,543.84 | ₹2,436.15 | Additive linear model cannot capture carrier × stop × layover interactions. |
| **Ridge Regression ($\alpha=1.0$)** | 71.52% | ₹1,546.91 | ₹2,436.92 | L2 penalty stabilizes sparse route coefficients without solving non-linearity. |
| **SVR (RBF Scaled)** | 77.92% | ₹1,058.16 | ₹2,145.41 | Adding `StandardScaler` boosted SVR from 0.30 (unscaled) to 0.7792. |
| **KNN Regressor (Scaled)** | 81.11% | ₹948.17 | ₹1,984.53 | Scaling numeric features boosted KNN from 0.56 (unscaled) to 0.8111. |
| **Decision Tree** | 84.99% | ₹750.69 | ₹1,769.34 | Captures non-linear splits but single tree has higher variance. |
| **Random Forest (Kaggle Base, 100 trees)** | 90.21% | ₹620.34 | ₹1,428.78 | Matches our Kaggle notebook (`lokii1929/airfare-prediction`) without data leakage. |
| **Random Forest (Tuned Final, 250 trees)** | **90.32%** | **₹619.93** | **₹1,420.35** | **Selected Production Model.** 5-Fold CV $R^2 = \mathbf{89.74\% \pm 1.47\%}$. |

---

## 3. Why Our Model Beat the Earlier 81.77% Version
1. **Kept `Route` and `Additional_Info`:** `Additional_Info` (e.g., *In-flight meal not included*, *Business class*, *No check-in baggage included*) and `Route` (128+ layover hub strings like `DEL → BOM → COK` vs `BLR → DEL`) explain over 8.5% additional variance.
2. **Preserved `New Delhi` vs `Delhi`:** In the 2019 dataset, `New Delhi` labels early-March peak bookings from Bangalore, which behave differently from April–June `Delhi` bookings.
3. **Deduplication & Leak-Free Pipeline:** Removing 220 exact duplicate rows prevented validation leakage and lowered MAE from ₹1,131 to ₹619.93. Putting `ColumnTransformer` inside `Pipeline` prevents any validation-set vocabulary leak during `OneHotEncoder.fit`.

---

## 4. Collection Dates & Market-Change Limitations (Exam Question Defense)
- **Collection Window:** March 2019 – June 2019 only (missing winter holiday peaks Oct–Dec).
- **Airline Industry Shifts:** `Jet Airways`, `GoAir`, and `Trujet` were active in early 2019; post-2019 shutdowns, Air India/Vistara mergers, and new carriers (Akasa Air) altered route pricing.
- **Inflation & Fuel Cost:** 2019 INR fares do not reflect post-2020 aviation turbine fuel (ATF) increases or airport fee inflation—handled transparently via our **Market Calibration Multiplier (1.00x vs 1.25x / 1.35x)** in the UI.
- **Missing Real-Time Signals:** The dataset does not contain days-to-departure (lead time) or live seat-bucket inventory.

---

## 5. Top Viva Questions & Concise Answers

1. **Why did you add `bcrypt` + `JWT` and 3 roles?**  
   To satisfy Stakeholder Usage (5 marks) with real authentication and role authorization (`Traveler` manages personal alerts/notes, `Analyst` exports CSV & audits benchmarks, `Admin` manages user roles & airline master tables) and avoid the `-5M` simple input-prediction penalty.
2. **How is your database in 3rd Normal Form (3NF)?**  
   Lookup attributes (city/state in `airports_master`, carrier code/tier in `airlines_master`, user email/role in `users`) live in master tables referenced via Foreign Keys from `flight_predictions` and `fare_alerts`, eliminating repeating groups and transitive dependencies.
3. **How do you compute the confidence range (`fare_lower` – `fare_upper`)?**  
   We collect the individual predictions across all 250 trees in `RandomForestRegressor.estimators_` and report the 25th–75th percentile (IQR) alongside the ensemble mean.
4. **Why is regression evaluated with $R^2$, MAE, RMSE instead of accuracy/confusion matrix?**  
   `Price` is a continuous numeric variable (₹1,759 to ₹79,512), not discrete class labels. Classification metrics like precision/recall apply only to categorical targets.
