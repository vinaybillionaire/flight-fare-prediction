"""
Flight Fare Prediction - Complete ML Training & Evaluation Pipeline
Flow Steps Implemented:
Step 1: Problem Definition
Step 2: Data Collection
Step 3: Data Preprocessing
Step 4: Exploratory Data Analysis (EDA) summary
Step 5: Feature Engineering
Step 6: Model Selection (Linear Regression, Ridge, Decision Tree, Random Forest)
Step 7: Model Training
Step 8: Model Evaluation (R2 Score, MAE, RMSE)
Step 9: Hyperparameter Tuning (RandomizedSearchCV)
Step 10: Model Saving (joblib serialization)
"""

import os
import json
import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "data", "Data_Train.csv")
MODELS_DIR = os.path.join(BASE_DIR, "models")

print("=" * 60)
print("Step 1: Problem Definition")
print("Objective: Predict airline flight ticket prices in India based on")
print("Airline, Route, Date of Journey, Source, Destination, Stops, and Duration.")
print("=" * 60)

print("\nStep 2: Data Collection")
df = pd.read_csv(DATA_PATH)
print(f"Loaded dataset successfully. Shape: {df.shape}")

print("\nStep 3: Data Preprocessing")
# Drop 1 null record in Route/Total_Stops
df.dropna(inplace=True)
print(f"Dataset shape after dropping nulls: {df.shape}")

# Normalize Destination 'New Delhi' -> 'Delhi' for consistency
df['Destination'] = df['Destination'].replace('New Delhi', 'Delhi')

print("\nStep 4: Exploratory Data Analysis & Step 5: Feature Engineering")

# 1. Date of Journey
df['Journey_day'] = pd.to_datetime(df['Date_of_Journey'], format="%d/%m/%Y").dt.day
df['Journey_month'] = pd.to_datetime(df['Date_of_Journey'], format="%d/%m/%Y").dt.month
df['Journey_weekday'] = pd.to_datetime(df['Date_of_Journey'], format="%d/%m/%Y").dt.weekday

# 2. Departure Time
df['Dep_hour'] = pd.to_datetime(df['Dep_Time'], format='%H:%M').dt.hour
df['Dep_min'] = pd.to_datetime(df['Dep_Time'], format='%H:%M').dt.minute

# 3. Arrival Time (extract time part)
df['Arrival_hour'] = pd.to_datetime(df['Arrival_Time'].str.split(' ').str[0], format='%H:%M').dt.hour
df['Arrival_min'] = pd.to_datetime(df['Arrival_Time'].str.split(' ').str[0], format='%H:%M').dt.minute

# 4. Duration into total minutes
def parse_duration(duration_str):
    parts = duration_str.split()
    hours = 0
    mins = 0
    for part in parts:
        if 'h' in part:
            hours = int(part.replace('h', ''))
        elif 'm' in part:
            mins = int(part.replace('m', ''))
    return hours * 60 + mins

df['Duration_mins'] = df['Duration'].apply(parse_duration)

# 5. Total Stops mapping (Ordinal feature)
stops_map = {
    'non-stop': 0,
    '1 stop': 1,
    '2 stops': 2,
    '3 stops': 3,
    '4 stops': 4
}
df['Total_Stops_Num'] = df['Total_Stops'].map(stops_map)

# Filter low frequency airlines if any, or keep standard top airlines
top_airlines = ['Jet Airways', 'IndiGo', 'Air India', 'Multiple carriers', 'SpiceJet', 'Vistara', 'Air Asia', 'GoAir']
df['Airline_Clean'] = df['Airline'].apply(lambda x: x if x in top_airlines else 'Other')

# Categorical One-Hot Encoding
airline_dummies = pd.get_dummies(df['Airline_Clean'], prefix='Airline', dtype=int)
source_dummies = pd.get_dummies(df['Source'], prefix='Source', dtype=int)
dest_dummies = pd.get_dummies(df['Destination'], prefix='Dest', dtype=int)

# Combine engineered features
numeric_features = [
    'Total_Stops_Num', 'Journey_day', 'Journey_month', 'Journey_weekday',
    'Dep_hour', 'Dep_min', 'Arrival_hour', 'Arrival_min', 'Duration_mins'
]

X = pd.concat([df[numeric_features], airline_dummies, source_dummies, dest_dummies], axis=1)
y = df['Price']

feature_columns = list(X.columns)
print(f"Total engineered features: {len(feature_columns)}")
print(f"Feature list: {feature_columns}")

# Save feature list for backend and inference
with open(os.path.join(MODELS_DIR, "feature_names.json"), "w") as f:
    json.dump(feature_columns, f, indent=2)

print("\nStep 6 & 7: Model Selection and Training (Comparing Algorithms)")
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
print(f"Train set: {X_train.shape}, Test set: {X_test.shape}")

models = {
    "Linear Regression": LinearRegression(),
    "Ridge Regression": Ridge(alpha=1.0),
    "Decision Tree": DecisionTreeRegressor(random_state=42, max_depth=15),
    "Random Forest": RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
}

comparison_results = {}

for name, model in models.items():
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    r2 = r2_score(y_test, y_pred)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    comparison_results[name] = {
        "R2_Score": round(float(r2), 4),
        "MAE": round(float(mae), 2),
        "RMSE": round(float(rmse), 2)
    }
    print(f"  [{name}] -> R2 Score: {r2:.4f} | MAE: Rs.{mae:.2f} | RMSE: Rs.{rmse:.2f}")

print("\nStep 9: Hyperparameter Tuning on Best Model (Random Forest)")
param_grid = {
    'n_estimators': [100, 150, 200],
    'max_depth': [15, 20, 25, None],
    'min_samples_split': [2, 5, 10],
    'min_samples_leaf': [1, 2, 4]
}

rf_base = RandomForestRegressor(random_state=42, n_jobs=-1)
rf_search = RandomizedSearchCV(
    estimator=rf_base,
    param_distributions=param_grid,
    n_iter=10,
    scoring='r2',
    cv=3,
    verbose=1,
    random_state=42,
    n_jobs=-1
)

rf_search.fit(X_train, y_train)
best_rf = rf_search.best_estimator_
print(f"Best Parameters: {rf_search.best_params_}")

y_pred_tuned = best_rf.predict(X_test)
tuned_r2 = r2_score(y_test, y_pred_tuned)
tuned_mae = mean_absolute_error(y_test, y_pred_tuned)
tuned_rmse = np.sqrt(mean_squared_error(y_test, y_pred_tuned))

print(f"\nStep 8: Final Model Evaluation (Tuned Random Forest)")
print(f"  Tuned R2 Score: {tuned_r2:.4f} ({tuned_r2*100:.2f}% accuracy)")
print(f"  Tuned MAE: Rs.{tuned_mae:.2f}")
print(f"  Tuned RMSE: Rs.{tuned_rmse:.2f}")

comparison_results["Tuned Random Forest (Final)"] = {
    "R2_Score": round(float(tuned_r2), 4),
    "MAE": round(float(tuned_mae), 2),
    "RMSE": round(float(tuned_rmse), 2)
}

# Save metrics
metrics_path = os.path.join(MODELS_DIR, "model_metrics.json")
with open(metrics_path, "w") as f:
    json.dump(comparison_results, f, indent=2)

print("\nStep 10: Model Saving")
model_path = os.path.join(MODELS_DIR, "flight_rf_model.pkl")
joblib.dump(best_rf, model_path)
print(f"Saved trained model to {model_path}")
print("Training Pipeline Complete!")
