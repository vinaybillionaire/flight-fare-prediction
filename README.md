# Airfare Price Estimation and Fare Pattern Analysis-II
**Academic Capstone Project | Group G1716**  
**Evaluation Date:** December 4th, 2026  
**Total Marks:** 50 (5 Marks Database Design + 45 Marks Project & Viva)

---

## 👥 Team Members (Group G1716)
- **25BD1A0589** - CHEEKATI VINAY
- **25BD1A0586** - BOMMINENI LOKESH NARAYANA
- **25BD1A058F** - DEVARSHETTY KARTHIK DATTA
- **25BD1A058Q** - KAMBOJI SAI DHANUSH KUMAR

**Mentor:** Padma Priya T  
**Tech Stack:** Python 3.14, FastAPI, Scikit-Learn, Random Forest, MySQL / SQLite, HTML5, CSS3, JavaScript

---

## 🛫 16-Step ML Model Design to URL Generation Flow
1. **Problem Definition** - Predict airfare in India from route, airline, stops, and schedule.
2. **Data Collection** - 10,682 verified flight records from Kaggle/MachineHack (`data/Data_Train.csv`).
3. **Data Preprocessing** - Missing value treatment & city normalization.
4. **Exploratory Data Analysis (EDA)** - Route, airline, and stop distribution analysis.
5. **Feature Engineering** - Date decomposition (day, month, weekday), duration in minutes, One-Hot Encoding (28 features).
6. **Model Selection** - Evaluated Linear Regression, Ridge, Decision Tree, and Random Forest.
7. **Model Training** - 80/20 train-test split (`models/train_models.py`).
8. **Model Evaluation** - $R^2 = 81.77\%$, $\text{MAE} = ₹1,131.59$, $\text{RMSE} = ₹1,982.37$.
9. **Hyperparameter Tuning** - RandomizedSearchCV (`n_estimators=200`, `max_depth=15`, `min_samples_split=2`).
10. **Model Saving** - Exported to `models/flight_rf_model.pkl` via `joblib`.
11. **Backend Development** - FastAPI REST endpoints (`backend/main.py`).
12. **Frontend Development** - Modern Linear-style prediction interface (`frontend/`).
13. **Model Integration** - Frontend asynchronous fetch wired to `/api/predict`.
14. **Testing** - Unit & integration test suite (`tests/test_suite.py`).
15. **Deployment** - Production Uvicorn web server runner (`run.py`).
16. **URL Generation** - Live access URL: **`http://127.0.0.1:8000`** & Interactive Docs: **`http://127.0.0.1:8000/docs`**.

---

## 🗄️ Database Design (5 Marks Deliverable)
- **MySQL Script:** Located at `database/schema.sql`.
- **Relational Design (3NF):**
  - `airports_master`: IATA codes, cities, states.
  - `airlines_master`: Carrier names, codes, active flags.
  - `flight_predictions`: Logs every prediction transaction with source, destination, stops, fare, and timestamp.
  - `model_benchmarks`: Benchmarking metrics across all 4 algorithms.
- **Portability:** Auto-fallback to local SQLite (`database/flight_fare.db`) if MySQL is offline, ensuring zero runtime crashes during evaluation.

---

## ⚡ How to Run the Project
```bash
# 1. Run the Web Application
python run.py

# 2. Open in Browser
http://127.0.0.1:8000

# 3. Run Automated Tests
python tests/test_suite.py

# 4. Re-train ML Model (Optional)
python models/train_models.py
```

---

## 📚 Viva Preparation
Read the full viva defense guide: [`viva/VIVA_QUESTIONS_AND_ANSWERS.md`](viva/VIVA_QUESTIONS_AND_ANSWERS.md)
Contains answers to 25+ evaluator questions, mathematical formula breakdowns, and code explanations.
