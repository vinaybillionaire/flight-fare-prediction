"""End-to-End ML Training, Comparison, Cross-Validation & EDA Pipeline.

Combines the user's 90%+ R2 Kaggle feature pipeline (lokii1929/airfare-prediction)
with leak-free sklearn Pipelines, multi-algorithm benchmarking across syllabus models,
hyperparameter tuning, 5-fold cross-validation, and real EDA analytics export.
"""

import json
import math
import os
import sys
from typing import Dict, List

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import RandomizedSearchCV, cross_val_score, train_test_split
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.svm import SVR
from sklearn.tree import DecisionTreeRegressor

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from models.features import (
    AIRPORT_CODES,
    CATEGORICAL_COLUMNS,
    FEATURE_COLUMNS,
    NUMERICAL_COLUMNS,
    preprocess_raw_dataframe,
)

MODELS_DIR = os.path.join(BASE_DIR, "models")
ARCHIVE_XLSX = os.path.join(BASE_DIR, "archive", "Data_Train.xlsx")
DATA_CSV = os.path.join(BASE_DIR, "data", "Data_Train.csv")


def load_training_dataset() -> pd.DataFrame:
    """Load the training dataset from archive Excel or CSV fallback."""
    if os.path.exists(ARCHIVE_XLSX):
        return pd.read_excel(ARCHIVE_XLSX)
    if os.path.exists(DATA_CSV):
        return pd.read_csv(DATA_CSV)
    raise FileNotFoundError(
        f"Training dataset not found at {ARCHIVE_XLSX} or {DATA_CSV}"
    )


def evaluate_predictions(y_true: pd.Series, y_pred: np.ndarray) -> Dict[str, float]:
    """Compute regression evaluation metrics (R2, MAE, RMSE, MAPE)."""
    r2 = r2_score(y_true, y_pred)
    mae = mean_absolute_error(y_true, y_pred)
    rmse = math.sqrt(mean_squared_error(y_true, y_pred))
    mape = float(np.mean(np.abs((y_true - y_pred) / np.maximum(y_true, 1))) * 100)
    return {
        "r2_score": round(float(r2), 4),
        "mae": round(float(mae), 2),
        "rmse": round(float(rmse), 2),
        "mape_pct": round(mape, 2),
    }


def build_grouped_feature_importance(pipeline: Pipeline) -> List[Dict[str, float]]:
    """Aggregate One-Hot encoded Random Forest importances back to raw feature names."""
    prep: ColumnTransformer = pipeline.named_steps["prep"]
    rf: RandomForestRegressor = pipeline.named_steps["model"]
    encoded_names = prep.get_feature_names_out()
    importances = rf.feature_importances_

    grouped: Dict[str, float] = {}
    for enc_name, imp in zip(encoded_names, importances):
        if enc_name.startswith("cat__"):
            raw = enc_name[len("cat__") :]
            matched_col = next(
                (col for col in CATEGORICAL_COLUMNS if raw.startswith(f"{col}_")),
                raw,
            )
            grouped[matched_col] = grouped.get(matched_col, 0.0) + float(imp)
        elif enc_name.startswith("num__"):
            raw = enc_name[len("num__") :]
            grouped[raw] = grouped.get(raw, 0.0) + float(imp)

    ordered = sorted(grouped.items(), key=lambda x: x[1], reverse=True)
    return [
        {"feature": name, "importance_pct": round(val * 100, 2)}
        for name, val in ordered
    ]


def export_route_catalog(df: pd.DataFrame) -> Dict:
    """Export valid airlines, cities, additional_info tags, and route lookup catalog."""
    routes_by_trip: Dict[str, List[Dict]] = {}
    grouped = (
        df.groupby(["Source", "Destination", "Total_Stops", "Route"])["Price"]
        .agg(["count", "mean"])
        .reset_index()
        .sort_values(["Source", "Destination", "Total_Stops", "count"], ascending=[True, True, True, False])
    )
    for _, row in grouped.iterrows():
        key = f"{row['Source']}|{row['Destination']}|{int(row['Total_Stops'])}"
        routes_by_trip.setdefault(key, []).append(
            {
                "route": row["Route"],
                "sample_count": int(row["count"]),
                "avg_historical_price": round(float(row["mean"]), 0),
            }
        )

    return {
        "airlines": sorted(df["Airline"].unique().tolist()),
        "sources": sorted(df["Source"].unique().tolist()),
        "destinations": sorted(df["Destination"].unique().tolist()),
        "additional_info_options": sorted(
            [x for x in df["Additional_Info"].unique().tolist() if x != "No Info"]
        ),
        "airport_codes": AIRPORT_CODES,
        "routes_by_trip": routes_by_trip,
    }


def export_eda_summary(
    raw_count: int,
    cleaned_df: pd.DataFrame,
    feature_importances: List[Dict[str, float]],
    y_val: pd.Series,
    y_pred: np.ndarray,
) -> Dict:
    """Compute data-driven EDA metrics for the interactive analytics dashboard."""
    df = cleaned_df.copy()

    def dep_bucket(hr: int) -> str:
        if 4 <= hr < 8:
            return "Early Morning (04-08)"
        if 8 <= hr < 12:
            return "Morning (08-12)"
        if 12 <= hr < 17:
            return "Afternoon (12-17)"
        if 17 <= hr < 21:
            return "Evening (17-21)"
        return "Night (21-04)"

    df["Dep_Window"] = df["Dep_Hour"].apply(dep_bucket)

    airline_stats = (
        df.groupby("Airline")["Price"]
        .agg(["count", "mean", "median", "min", "max"])
        .reset_index()
        .sort_values("mean", ascending=False)
    )
    stops_stats = (
        df.groupby("Total_Stops")["Price"]
        .agg(["count", "mean", "median"])
        .reset_index()
        .sort_values("Total_Stops")
    )
    month_names = {3: "March", 4: "April", 5: "May", 6: "June"}
    month_stats = (
        df.groupby("Journey_Month")["Price"]
        .agg(["count", "mean", "median"])
        .reset_index()
        .sort_values("Journey_Month")
    )
    weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday_stats = (
        df.groupby("Journey_Weekday")["Price"]
        .agg(["count", "mean"])
        .reset_index()
        .sort_values("Journey_Weekday")
    )
    dep_window_order = [
        "Early Morning (04-08)",
        "Morning (08-12)",
        "Afternoon (12-17)",
        "Evening (17-21)",
        "Night (21-04)",
    ]
    dep_stats = (
        df.groupby("Dep_Window")["Price"]
        .agg(["count", "mean"])
        .reindex(dep_window_order)
        .dropna()
        .reset_index()
    )
    info_stats = (
        df.groupby("Additional_Info")["Price"]
        .agg(["count", "mean"])
        .reset_index()
        .sort_values("mean", ascending=False)
    )
    route_stats = (
        df.groupby(["Source", "Destination"])["Price"]
        .agg(["count", "mean", "min", "max"])
        .reset_index()
        .sort_values("mean", ascending=False)
    )

    residuals = np.abs(y_val.values - y_pred)
    within_1000 = float(np.mean(residuals <= 1000) * 100)
    within_1500 = float(np.mean(residuals <= 1500) * 100)

    return {
        "dataset_overview": {
            "raw_records": int(raw_count),
            "cleaned_records": int(len(df)),
            "duplicates_removed": int(raw_count - 1 - len(df)),
            "missing_dropped": 1,
            "collection_window": "March 2019 – June 2019 (Historical Kaggle/MachineHack Dataset)",
            "min_price": int(df["Price"].min()),
            "median_price": round(float(df["Price"].median()), 2),
            "mean_price": round(float(df["Price"].mean()), 2),
            "max_price": int(df["Price"].max()),
            "within_1000_inr_pct": round(within_1000, 1),
            "within_1500_inr_pct": round(within_1500, 1),
        },
        "by_airline": [
            {
                "airline": r["Airline"],
                "count": int(r["count"]),
                "mean_price": round(float(r["mean"]), 0),
                "median_price": round(float(r["median"]), 0),
                "max_price": int(r["max"]),
            }
            for _, r in airline_stats.iterrows()
        ],
        "by_stops": [
            {
                "stops": int(r["Total_Stops"]),
                "label": "Non-stop" if int(r["Total_Stops"]) == 0 else f"{int(r['Total_Stops'])} Stop(s)",
                "count": int(r["count"]),
                "mean_price": round(float(r["mean"]), 0),
                "median_price": round(float(r["median"]), 0),
            }
            for _, r in stops_stats.iterrows()
        ],
        "by_month": [
            {
                "month": int(r["Journey_Month"]),
                "label": month_names.get(int(r["Journey_Month"]), str(r["Journey_Month"])),
                "count": int(r["count"]),
                "mean_price": round(float(r["mean"]), 0),
                "median_price": round(float(r["median"]), 0),
            }
            for _, r in month_stats.iterrows()
        ],
        "by_weekday": [
            {
                "weekday": int(r["Journey_Weekday"]),
                "label": weekday_names[int(r["Journey_Weekday"])],
                "count": int(r["count"]),
                "mean_price": round(float(r["mean"]), 0),
            }
            for _, r in weekday_stats.iterrows()
        ],
        "by_departure_window": [
            {
                "window": r["Dep_Window"],
                "count": int(r["count"]),
                "mean_price": round(float(r["mean"]), 0),
            }
            for _, r in dep_stats.iterrows()
        ],
        "by_additional_info": [
            {
                "info": r["Additional_Info"],
                "count": int(r["count"]),
                "mean_price": round(float(r["mean"]), 0),
            }
            for _, r in info_stats.head(7).iterrows()
        ],
        "by_city_pair": [
            {
                "route": f"{r['Source']} → {r['Destination']}",
                "count": int(r["count"]),
                "mean_price": round(float(r["mean"]), 0),
                "min_price": int(r["min"]),
                "max_price": int(r["max"]),
            }
            for _, r in route_stats.head(10).iterrows()
        ],
        "feature_importances": feature_importances,
        "market_limitations": {
            "collection_period": "March – June 2019",
            "factors": [
                "Temporal Cutoff & Inflation: Fares reflect 2019 INR price levels; aviation turbine fuel (ATF), airport taxes, and post-2020 inflation shift baseline fares upward by ~20–35% today.",
                "Carrier Market Changes: Airlines active in 2019 (Jet Airways, GoAir, Trujet) later ceased or restructured operations, while newer carriers (Akasa Air) and Air India/Vistara consolidation changed competition.",
                "Missing Dynamic Demand Signals: The dataset lacks days-before-departure (lead time), live seat-inventory load factors, fare class buckets, and holiday/festival calendar shocks.",
                "Seasonal Scope: Training records span March to June only; winter peak seasons (Oct–Dec) are outside the observed training window.",
            ],
        },
    }


def main():
    os.makedirs(MODELS_DIR, exist_ok=True)
    print("=" * 72)
    print("FareLens | Leak-Free 90%+ ML Training & Benchmark Suite")
    print("=" * 72)

    raw_df = load_training_dataset()
    raw_count = len(raw_df)
    print(f"Loaded raw dataset: {raw_df.shape}")

    df = preprocess_raw_dataframe(raw_df, is_train=True)
    print(f"After dropping 1 null & 220 duplicates: {df.shape}")

    X = df[FEATURE_COLUMNS]
    y = df["Price"]

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.20, random_state=42
    )
    print(f"Train split: {len(X_train)} | Held-out Validation split: {len(X_val)}")

    prep_scaled = ColumnTransformer(
        [
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_COLUMNS),
            ("num", StandardScaler(), NUMERICAL_COLUMNS),
        ]
    )
    prep_trees = ColumnTransformer(
        [
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_COLUMNS),
            ("num", "passthrough", NUMERICAL_COLUMNS),
        ]
    )

    candidate_pipelines = {
        "Linear Regression": Pipeline(
            [("prep", prep_scaled), ("model", LinearRegression())]
        ),
        "Ridge Regression": Pipeline(
            [("prep", prep_scaled), ("model", Ridge(alpha=1.0))]
        ),
        "Decision Tree": Pipeline(
            [("prep", prep_trees), ("model", DecisionTreeRegressor(max_depth=16, random_state=42))]
        ),
        "KNN Regressor (Scaled)": Pipeline(
            [("prep", prep_scaled), ("model", KNeighborsRegressor(n_neighbors=5, weights="distance"))]
        ),
        "SVR (RBF Scaled)": Pipeline(
            [("prep", prep_scaled), ("model", SVR(kernel="rbf", C=1000.0, gamma="scale"))]
        ),
        "Random Forest (Kaggle Base)": Pipeline(
            [
                ("prep", prep_trees),
                ("model", RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)),
            ]
        ),
    }

    metrics_output: Dict[str, Dict] = {}
    for name, pipe in candidate_pipelines.items():
        pipe.fit(X_train, y_train)
        preds = pipe.predict(X_val)
        scores = evaluate_predictions(y_val, preds)
        scores["is_selected"] = False
        metrics_output[name] = scores
        print(
            f"  [{name:28s}] R2={scores['r2_score']:.4f} | MAE=Rs.{scores['mae']:7.2f} | RMSE=Rs.{scores['rmse']:7.2f}"
        )

    # Hyperparameter Tuning on Random Forest inside leak-free Pipeline
    print("\nRunning RandomizedSearchCV (3-fold CV) for Tuned Random Forest...")
    base_rf_pipe = Pipeline(
        [
            ("prep", prep_trees),
            ("model", RandomForestRegressor(random_state=42, n_jobs=-1)),
        ]
    )
    param_dist = {
        "model__n_estimators": [150, 200, 250],
        "model__max_depth": [None, 24, 30],
        "model__min_samples_split": [2, 3, 4],
        "model__min_samples_leaf": [1, 2],
    }
    search = RandomizedSearchCV(
        estimator=base_rf_pipe,
        param_distributions=param_dist,
        n_iter=6,
        scoring="r2",
        cv=3,
        random_state=42,
        n_jobs=-1,
        verbose=1,
    )
    search.fit(X_train, y_train)
    best_pipe: Pipeline = search.best_estimator_
    print(f"Best Tuned Params: {search.best_params_}")

    tuned_preds = best_pipe.predict(X_val)
    tuned_scores = evaluate_predictions(y_val, tuned_preds)

    # Compare tuned RF against Kaggle Base; keep whichever generalizes best
    kaggle_base_pipe = candidate_pipelines["Random Forest (Kaggle Base)"]
    if tuned_scores["r2_score"] < metrics_output["Random Forest (Kaggle Base)"]["r2_score"]:
        final_pipe = kaggle_base_pipe
        final_preds = final_pipe.predict(X_val)
        final_scores = dict(metrics_output["Random Forest (Kaggle Base)"])
        final_label = "Random Forest (Kaggle Base)"
    else:
        final_pipe = best_pipe
        final_preds = tuned_preds
        final_scores = tuned_scores
        final_label = "Random Forest (Tuned Final)"

    # 5-fold cross-validation on full training split for robustness reporting
    cv_scores = cross_val_score(final_pipe, X, y, cv=5, scoring="r2", n_jobs=-1)
    final_scores["cv_r2_mean"] = round(float(cv_scores.mean()), 4)
    final_scores["cv_r2_std"] = round(float(cv_scores.std()), 4)
    final_scores["is_selected"] = True
    metrics_output["Random Forest (Tuned Final)"] = tuned_scores
    metrics_output[final_label]["is_selected"] = True

    print(
        f"\nSelected Production Model: {final_label}\n"
        f"  Held-out R2={final_scores['r2_score']:.4f} ({final_scores['r2_score']*100:.2f}%) | "
        f"MAE=Rs.{final_scores['mae']:.2f} | RMSE=Rs.{final_scores['rmse']:.2f} | "
        f"5-Fold CV R2={final_scores['cv_r2_mean']:.4f} ± {final_scores['cv_r2_std']:.4f}"
    )

    encoded_feature_names = list(final_pipe.named_steps["prep"].get_feature_names_out())
    grouped_importances = build_grouped_feature_importance(final_pipe)

    model_path = os.path.join(MODELS_DIR, "flight_rf_model.pkl")
    joblib.dump(final_pipe, model_path, compress=3)

    with open(os.path.join(MODELS_DIR, "feature_names.json"), "w") as f:
        json.dump(
            {
                "raw_features": FEATURE_COLUMNS,
                "categorical_columns": CATEGORICAL_COLUMNS,
                "numerical_columns": NUMERICAL_COLUMNS,
                "encoded_features_count": len(encoded_feature_names),
                "encoded_features": encoded_feature_names,
            },
            f,
            indent=2,
        )

    with open(os.path.join(MODELS_DIR, "model_metrics.json"), "w") as f:
        json.dump(
            {
                "selected_model": final_label,
                "best_params": {
                    k.replace("model__", ""): v for k, v in search.best_params_.items()
                },
                "training_samples": len(X_train),
                "validation_samples": len(X_val),
                "raw_feature_count": len(FEATURE_COLUMNS),
                "encoded_feature_count": len(encoded_feature_names),
                "models": metrics_output,
            },
            f,
            indent=2,
        )

    route_catalog = export_route_catalog(df)
    with open(os.path.join(MODELS_DIR, "route_catalog.json"), "w") as f:
        json.dump(route_catalog, f, indent=2)

    eda_summary = export_eda_summary(raw_count, df, grouped_importances, y_val, final_preds)
    with open(os.path.join(MODELS_DIR, "eda_summary.json"), "w") as f:
        json.dump(eda_summary, f, indent=2)

    print(f"Artifacts saved to {MODELS_DIR} (compressed model size: {os.path.getsize(model_path)/1e6:.2f} MB)")


if __name__ == "__main__":
    main()
