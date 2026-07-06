"""
forecasting.py
==============
LightGBM-only weekly-demand forecasting with quantile regression prediction intervals.

For each Store_ID × SKU_ID time series:
  * Train a global LightGBM point-forecast model (objective='regression').
  * Train global lower-bound (q10) and upper-bound (q90) quantile regression models.
  * Hold out the last 6 weeks for validation; retrain on full history for final forecast.
  * Forecast the next 6 weeks with recursive multi-step prediction.
  * Derive Total_Sales and Total_Margin from forecast quantity × price/cost per SKU.

Outputs written to Outputs/:
  * Forecast_Validation.csv  — per-series validation MAE
  * Forecast_Output.csv      — 6-week forecasts with prediction intervals + Sales/Margin
"""

import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# DB import (try; fall back gracefully if not available)
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
try:
    from database.connection import read_table_or_csv as _db_read
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(BASE_DIR)))
INPUT_XLSX        = os.path.join(PROJECT_DIR, "Outputs", "weekly_demand_output.xlsx")
INPUT_CSV         = os.path.join(PROJECT_DIR, "Outputs", "weekly_demand_output.csv")
VALIDATION_OUTPUT = os.path.join(PROJECT_DIR, "Outputs", "Forecast_Validation.csv")
FORECAST_OUTPUT   = os.path.join(PROJECT_DIR, "Outputs", "Forecast_Output.csv")

SKU_MASTER    = os.path.join(PROJECT_DIR, "Raw_Input", "SKU_Master.csv")
STORE_MASTER  = os.path.join(PROJECT_DIR, "Raw_Input", "Store_Master.csv")
STORE_CLUSTER = os.path.join(PROJECT_DIR, "Outputs", "store_clusters.csv")

REQUIRED_COLUMNS = ["Year_WK", "Store_ID", "SKU_ID", "Quantity_Sold"]

MIN_WEEKS = 12
HORIZON   = 6

LGB_FEATURES = [
    "Year", "Week_Number", "Month_Number", "Quarter",
    "Store_ID_enc", "SKU_ID_enc",
    "lag_1", "lag_2", "lag_4",
    "rolling_mean_4", "rolling_mean_8", "rolling_std_4",
]

# Point forecast (conditional mean)
LGB_PARAMS = dict(
    objective="regression",
    n_estimators=500,
    learning_rate=0.05,
    num_leaves=31,
    max_depth=-1,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    verbosity=-1,
)

# 10th-percentile lower bound
LGB_PARAMS_LOWER = dict(
    objective="quantile",
    alpha=0.10,
    n_estimators=500,
    learning_rate=0.05,
    num_leaves=31,
    max_depth=-1,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    verbosity=-1,
)

# 90th-percentile upper bound
LGB_PARAMS_UPPER = dict(
    objective="quantile",
    alpha=0.90,
    n_estimators=500,
    learning_rate=0.05,
    num_leaves=31,
    max_depth=-1,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    verbosity=-1,
)


# ===========================================================================
# 1. LOAD
# ===========================================================================
def load_data():
    if _DB_AVAILABLE:
        # Try PostgreSQL first; csv_path = XLSX preferred, CSV as next fallback
        _csv_path = Path(INPUT_XLSX) if os.path.isfile(INPUT_XLSX) else Path(INPUT_CSV)
        df = _db_read("weekly_demand_output", _csv_path)
        if not df.empty:
            source = "PostgreSQL (or file fallback)"
            print(f"[load_data] Loaded {len(df):,} rows from {source}.")
        else:
            raise FileNotFoundError(
                f"weekly_demand_output not found in PostgreSQL and no file at {_csv_path}."
            )
    elif os.path.isfile(INPUT_XLSX):
        df = pd.read_excel(INPUT_XLSX)
        source = INPUT_XLSX
    elif os.path.isfile(INPUT_CSV):
        df = pd.read_csv(INPUT_CSV)
        source = INPUT_CSV
        print(f"[load_data] NOTE: {os.path.basename(INPUT_XLSX)} not found; "
              f"falling back to {os.path.basename(INPUT_CSV)}.")
    else:
        raise FileNotFoundError(
            f"Input file not found. Expected: {INPUT_XLSX} (or {INPUT_CSV})."
        )

    if df.empty:
        raise ValueError("Input file contains no rows.")

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise KeyError(f"Input is missing required columns: {missing}. "
                       f"Available: {list(df.columns)}")

    print(f"[load_data] Loaded {len(df):,} rows from {os.path.basename(source)}.")
    return df


# ===========================================================================
# 2. PREPARE
# ===========================================================================
def prepare_data(df):
    df = df[REQUIRED_COLUMNS].copy()

    df["date"] = pd.to_datetime(
        df["Year_WK"].astype(str).str.strip() + "-1", format="%G-%V-%u", errors="coerce"
    )
    n_bad = df["date"].isna().sum()
    if n_bad == len(df):
        raise ValueError("No valid Year_WK values could be parsed. Expected ISO format like '2026-32'.")
    if n_bad > 0:
        print(f"[prepare_data] WARNING: dropping {n_bad:,} rows with invalid Year_WK.")
        df = df.dropna(subset=["date"])

    iso = df["date"].dt.isocalendar()
    df["Year"]         = df["date"].dt.year
    df["Week_Number"]  = iso["week"].astype(int)
    df["Month_Number"] = df["date"].dt.month
    df["Quarter"]      = df["date"].dt.quarter

    df["unique_id"] = df["Store_ID"].astype(str) + "_" + df["SKU_ID"].astype(str)
    df["Quantity_Sold"] = pd.to_numeric(df["Quantity_Sold"], errors="coerce").fillna(0)
    df = df.sort_values(["unique_id", "date"]).reset_index(drop=True)

    counts = df.groupby("unique_id")["date"].transform("count")
    too_short = df.loc[counts < MIN_WEEKS, "unique_id"].nunique()
    if too_short > 0:
        print(f"[prepare_data] Dropping {too_short} series with < {MIN_WEEKS} weeks of history.")
    df = df[counts >= MIN_WEEKS].reset_index(drop=True)

    if df.empty:
        raise ValueError(f"No series have >= {MIN_WEEKS} weeks of history.")
    return df


# ===========================================================================
# 3. FEATURE ENGINEERING
# ===========================================================================
def create_lightgbm_features(df):
    df = df.copy()
    df["Store_ID_enc"] = df["Store_ID"].astype("category").cat.codes
    df["SKU_ID_enc"]   = df["SKU_ID"].astype("category").cat.codes
    store_map = dict(zip(df["Store_ID"], df["Store_ID_enc"]))
    sku_map   = dict(zip(df["SKU_ID"],   df["SKU_ID_enc"]))

    g = df.groupby("unique_id")["Quantity_Sold"]
    df["lag_1"] = g.shift(1)
    df["lag_2"] = g.shift(2)
    df["lag_4"] = g.shift(4)

    shifted = g.shift(1)
    df["rolling_mean_4"] = shifted.groupby(df["unique_id"]).rolling(4).mean().reset_index(level=0, drop=True)
    df["rolling_mean_8"] = shifted.groupby(df["unique_id"]).rolling(8).mean().reset_index(level=0, drop=True)
    df["rolling_std_4"]  = shifted.groupby(df["unique_id"]).rolling(4).std().reset_index(level=0, drop=True)

    return df, store_map, sku_map


def _build_step_features(history_y, target_date, store_enc, sku_enc):
    iso_year, iso_week, _ = target_date.isocalendar()
    return {
        "Year":           iso_year,
        "Week_Number":    int(iso_week),
        "Month_Number":   target_date.month,
        "Quarter":        (target_date.month - 1) // 3 + 1,
        "Store_ID_enc":   store_enc,
        "SKU_ID_enc":     sku_enc,
        "lag_1":          history_y[-1],
        "lag_2":          history_y[-2],
        "lag_4":          history_y[-4],
        "rolling_mean_4": float(np.mean(history_y[-4:])),
        "rolling_mean_8": float(np.mean(history_y[-8:])),
        "rolling_std_4":  float(np.std(history_y[-4:], ddof=1)),
    }


def _recursive_forecast(model, history_y, last_date, store_enc, sku_enc, horizon):
    """Recursive multi-step point forecast; appends each prediction to the running history."""
    ys       = list(history_y)
    cur_date = pd.Timestamp(last_date)
    out      = []
    for _ in range(horizon):
        cur_date = cur_date + pd.Timedelta(weeks=1)
        feats    = _build_step_features(ys, cur_date, store_enc, sku_enc)
        X        = pd.DataFrame([feats])[LGB_FEATURES]
        pred     = max(0.0, float(model.predict(X)[0]))
        ys.append(pred)
        out.append((cur_date, pred))
    return out


# ===========================================================================
# 3a. LIGHTGBM VALIDATE
# ===========================================================================
def train_validate_lightgbm(df, store_map, sku_map):
    try:
        from lightgbm import LGBMRegressor
    except ImportError:
        print("[LightGBM] Package not installed. Install with `pip install lightgbm`.")
        return None

    df = df.copy()
    df["rank_from_end"] = df.groupby("unique_id")["date"].rank(method="first", ascending=False)
    train_mask = df["rank_from_end"] > HORIZON
    train_df   = df[train_mask].dropna(subset=LGB_FEATURES)

    if train_df.empty:
        print("[LightGBM] No usable training rows. Skipping validation.")
        return None

    model = LGBMRegressor(**LGB_PARAMS)
    model.fit(train_df[LGB_FEATURES], train_df["Quantity_Sold"])

    mae = {}
    for uid, grp in df.groupby("unique_id"):
        grp        = grp.sort_values("date")
        train_part = grp[grp["rank_from_end"] > HORIZON]
        valid_part = grp[grp["rank_from_end"] <= HORIZON]
        if len(valid_part) < HORIZON or train_part.empty:
            continue
        history_y = train_part["Quantity_Sold"].tolist()
        preds     = _recursive_forecast(
            model, history_y, train_part["date"].iloc[-1],
            store_map[grp["Store_ID"].iloc[0]], sku_map[grp["SKU_ID"].iloc[0]], HORIZON,
        )
        pred_vals = np.array([p for _, p in preds])
        actual    = valid_part["Quantity_Sold"].to_numpy()
        mae[uid]  = float(np.mean(np.abs(pred_vals - actual)))

    print(f"[LightGBM] Validated {len(mae)} series.")
    return mae


# ===========================================================================
# 3b. LIGHTGBM FORECAST  (point + q10/q90 quantile bounds)
# ===========================================================================
def forecast_lightgbm(df, store_map, sku_map):
    try:
        from lightgbm import LGBMRegressor
    except ImportError:
        return None

    full_train = df.dropna(subset=LGB_FEATURES)

    # Three models: point, lower (q10), upper (q90)
    model_pt = LGBMRegressor(**LGB_PARAMS)
    model_pt.fit(full_train[LGB_FEATURES], full_train["Quantity_Sold"])

    model_lo = LGBMRegressor(**LGB_PARAMS_LOWER)
    model_lo.fit(full_train[LGB_FEATURES], full_train["Quantity_Sold"])

    model_hi = LGBMRegressor(**LGB_PARAMS_UPPER)
    model_hi.fit(full_train[LGB_FEATURES], full_train["Quantity_Sold"])

    rows = []
    for uid, grp in df.groupby("unique_id"):
        grp       = grp.sort_values("date")
        history_y = grp["Quantity_Sold"].tolist()
        store_id  = grp["Store_ID"].iloc[0]
        sku_id    = grp["SKU_ID"].iloc[0]
        se        = store_map[store_id]
        ske       = sku_map[sku_id]
        last_date = grp["date"].iloc[-1]

        # Point forecast drives the recursive history for all models
        preds_pt = _recursive_forecast(model_pt, history_y, last_date, se, ske, HORIZON)

        # Quantile bounds: use point-forecast history for lag features (avoids quantile divergence)
        preds_lo, preds_hi = [], []
        for i, (ds, val_pt) in enumerate(preds_pt):
            hist_i = history_y + [p for _, p in preds_pt[:i]]
            feats  = _build_step_features(hist_i, ds, se, ske)
            X      = pd.DataFrame([feats])[LGB_FEATURES]
            lo     = max(0.0, float(model_lo.predict(X)[0]))
            hi     = max(0.0, float(model_hi.predict(X)[0]))
            # Enforce monotonicity: lo ≤ point ≤ hi
            lo = min(lo, val_pt)
            hi = max(hi, val_pt)
            preds_lo.append((ds, lo))
            preds_hi.append((ds, hi))

        for (ds, val_pt), (_, val_lo), (_, val_hi) in zip(preds_pt, preds_lo, preds_hi):
            rows.append({
                "unique_id":         uid,
                "Store_ID":          store_id,
                "SKU_ID":            sku_id,
                "ds":                ds,
                "LightGBM_Forecast": val_pt,
                "Forecast_Lower":    val_lo,
                "Forecast_Upper":    val_hi,
            })

    print(f"[LightGBM] Forecasted next {HORIZON} weeks for "
          f"{df['unique_id'].nunique()} series (point + Q10/Q90 bounds).")
    return pd.DataFrame(rows)


# ===========================================================================
# 4. ASSEMBLE OUTPUTS
# ===========================================================================
def _ds_to_year_wk(ts):
    y, w, _ = pd.Timestamp(ts).isocalendar()
    return f"{y}-{int(w):02d}"


def compare_models(df, lgb_mae, lgb_fc):
    """Build validation and forecast tables (LightGBM only)."""
    series = df[["unique_id", "Store_ID", "SKU_ID"]].drop_duplicates().reset_index(drop=True)

    val = series.copy()
    val["LightGBM_MAE"] = val["unique_id"].map(lgb_mae or {})
    val["Best_Model"]   = "LightGBM"
    validation_df = val[["Store_ID", "SKU_ID", "unique_id", "LightGBM_MAE", "Best_Model"]]

    if lgb_fc is None:
        raise RuntimeError("LightGBM forecast failed — no forecasts to write.")

    fc = lgb_fc.copy()
    fc["Final_Forecast"] = fc["LightGBM_Forecast"]
    fc["Selected_Model"] = "LightGBM"
    fc["Forecast_Week"]  = fc["ds"].apply(_ds_to_year_wk)
    fc = fc.sort_values(["Store_ID", "SKU_ID", "ds"])

    forecast_df = fc[[
        "Forecast_Week", "Store_ID", "SKU_ID", "unique_id",
        "LightGBM_Forecast", "Forecast_Lower", "Forecast_Upper",
        "Final_Forecast", "Selected_Model",
    ]].reset_index(drop=True)

    return validation_df, forecast_df


# ===========================================================================
# 5. ENRICH
# ===========================================================================
def enrich_forecast(forecast_df):
    """
    Join SKU hierarchy + pricing (List_Price_USD, Unit_Cost_USD), store attributes,
    and cluster label.  Derive Total_Sales and Total_Margin with their Q10/Q90 bounds.
    """
    df = forecast_df.copy()

    # SKU hierarchy + pricing
    sku_cols = ["SKU_ID", "Ownership", "Category", "Sub_Category",
                "Segment", "Attribute_Claim", "Brand",
                "List_Price_USD", "Unit_Cost_USD"]
    try:
        if _DB_AVAILABLE:
            sku_master = _db_read("sku_master", Path(SKU_MASTER))
        else:
            sku_master = pd.read_csv(SKU_MASTER)
        if not sku_master.empty:
            fetch = [c for c in sku_cols if c in sku_master.columns]
            df = df.merge(sku_master[fetch], on="SKU_ID", how="left")
            print(f"[enrich_forecast] Merged SKU attributes.")
        else:
            raise FileNotFoundError
    except FileNotFoundError:
        print(f"[enrich_forecast] WARNING: sku_master not found — SKU attributes blank.")
        for c in sku_cols[1:]:
            df[c] = np.nan

    # Store attributes
    store_cols = ["Store_ID", "Geography", "Region"]
    try:
        if _DB_AVAILABLE:
            store_master = _db_read("store_master", Path(STORE_MASTER))
        else:
            store_master = pd.read_csv(STORE_MASTER)
        if not store_master.empty:
            fetch = [c for c in store_cols if c in store_master.columns]
            df = df.merge(store_master[fetch], on="Store_ID", how="left")
            print(f"[enrich_forecast] Merged store attributes.")
        else:
            raise FileNotFoundError
    except FileNotFoundError:
        print(f"[enrich_forecast] WARNING: store_master not found — store attributes blank.")
        for c in store_cols[1:]:
            df[c] = np.nan

    # Store cluster
    try:
        if _DB_AVAILABLE:
            store_cluster = _db_read("store_clusters", Path(STORE_CLUSTER))
        else:
            store_cluster = pd.read_csv(STORE_CLUSTER)
        if not store_cluster.empty and "Cluster_Label" in store_cluster.columns:
            store_cluster = store_cluster[["Store_ID", "Cluster_Label"]].rename(
                columns={"Cluster_Label": "Cluster"}
            )
            df = df.merge(store_cluster, on="Store_ID", how="left")
            print(f"[enrich_forecast] Merged cluster labels.")
        else:
            raise FileNotFoundError
    except FileNotFoundError:
        print(f"[enrich_forecast] WARNING: store_clusters not found — Cluster blank.")
        df["Cluster"] = np.nan

    # Derive Sales and Margin with prediction interval propagation
    price          = pd.to_numeric(df.get("List_Price_USD",  0), errors="coerce").fillna(0)
    cost           = pd.to_numeric(df.get("Unit_Cost_USD",   0), errors="coerce").fillna(0)
    margin_per_unit = price - cost

    df["Total_Sales"]         = (df["Final_Forecast"]  * price).round(2)
    df["Total_Sales_Lower"]   = (df["Forecast_Lower"]  * price).round(2)
    df["Total_Sales_Upper"]   = (df["Forecast_Upper"]  * price).round(2)
    df["Total_Margin"]        = (df["Final_Forecast"]  * margin_per_unit).round(2)
    df["Total_Margin_Lower"]  = (df["Forecast_Lower"]  * margin_per_unit).round(2)
    df["Total_Margin_Upper"]  = (df["Forecast_Upper"]  * margin_per_unit).round(2)

    ordered_cols = [
        "Forecast_Week", "Store_ID", "SKU_ID", "unique_id",
        "Geography", "Region", "Cluster",
        "Ownership", "Category", "Sub_Category", "Segment", "Attribute_Claim", "Brand",
        "List_Price_USD", "Unit_Cost_USD",
        "LightGBM_Forecast", "Forecast_Lower", "Forecast_Upper",
        "Final_Forecast", "Selected_Model",
        "Total_Sales", "Total_Sales_Lower", "Total_Sales_Upper",
        "Total_Margin", "Total_Margin_Lower", "Total_Margin_Upper",
    ]
    df = df[[c for c in ordered_cols if c in df.columns]]
    return df


# ===========================================================================
# 6. SAVE + SUMMARY
# ===========================================================================
def save_outputs(validation_df, forecast_df):
    validation_df.to_csv(VALIDATION_OUTPUT, index=False)
    forecast_df.to_csv(FORECAST_OUTPUT, index=False)
    print(f"[save_outputs] Wrote {VALIDATION_OUTPUT}")
    print(f"[save_outputs] Wrote {FORECAST_OUTPUT}")


def _mae_summary(mae_dict, label):
    if not mae_dict:
        print(f"  {label}: not available")
        return
    vals = np.array(list(mae_dict.values()), dtype=float)
    print(f"  {label}: series={len(vals)}  mean={vals.mean():.2f}  "
          f"median={np.median(vals):.2f}  min={vals.min():.2f}  max={vals.max():.2f}")


# ===========================================================================
# MAIN
# ===========================================================================
def main():
    try:
        raw      = load_data()
        prepared = prepare_data(raw)
        feat_df, store_map, sku_map = create_lightgbm_features(prepared)

        n_rows        = len(prepared)
        n_combos_total = prepared["unique_id"].nunique()

        lgb_mae = train_validate_lightgbm(feat_df, store_map, sku_map)
        lgb_fc  = forecast_lightgbm(feat_df, store_map, sku_map)

        validation_df, forecast_df = compare_models(prepared, lgb_mae, lgb_fc)
        forecast_df = enrich_forecast(forecast_df)
        save_outputs(validation_df, forecast_df)

        print("\n================= SUMMARY =================")
        print(f"Rows loaded:                      {n_rows:,}")
        print(f"Unique Store_ID+SKU_ID combos:    {n_combos_total}")
        print(f"Combinations used for modeling:   {validation_df['unique_id'].nunique()}")
        print("Validation MAE:")
        _mae_summary(lgb_mae, "LightGBM")
        print("Output files:")
        print(f"  {VALIDATION_OUTPUT}")
        print(f"  {FORECAST_OUTPUT}")
        print("===========================================")

    except (FileNotFoundError, KeyError, ValueError, RuntimeError) as err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
