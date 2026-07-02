"""
cluster.py
==========
Hierarchical store clustering from Store_Master.csv.

Scalability strategy
--------------------
  n  <= 500 stores  : scipy Ward linkage runs directly on all n points.
                      Memory is O(n^2); at 500 stores that is ~1 MB — fine.
  n  > 500 stores   : BIRCH pre-clusters the data into ~sqrt(n) compact
                      sub-centroids first, then Ward linkage runs on those
                      centroids.  Memory drops from O(n^2) to O(sqrt(n)^2),
                      letting the same code handle 10,000+ stores without
                      major modification.  PCA is also applied above this
                      threshold to reduce feature dimensionality while
                      retaining >= 95% of variance.

Outputs (written to the same directory as Store_Master.csv)
-----------------------------------------------------------
  store_clusters.csv          Store_ID, Cluster_ID, Cluster_Label
  store_clusters_summary.json Cluster metadata (label, description, stats)

Optional output
---------------
  If the React app path (REACT_DATA_DIR) resolves to an existing directory,
  the script also writes src/data/storeClusters.js — an ES-module that the
  React filter can import directly.

Usage
-----
  python cluster.py                        # defaults
  python cluster.py --n_clusters 4         # force k=4
  python cluster.py --store_file path.csv  # custom input
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------------------
# DB import (try; fall back gracefully if not available)
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
try:
    from db import read_table_or_csv as _db_read
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Prefer Raw_Input/Store_Master.csv; keep legacy path as fallback
_PROJECT_DIR = os.path.dirname(os.path.dirname(BASE_DIR))
STORE_FILE = os.path.join(_PROJECT_DIR, "Raw_Input", "Store_Master.csv")
if not os.path.isfile(STORE_FILE):
    STORE_FILE = os.path.join(BASE_DIR, "Store_Master.csv")
CLUSTER_CSV = os.path.join(BASE_DIR, "store_clusters.csv")
CLUSTER_JSON = os.path.join(BASE_DIR, "store_clusters_summary.json")

# Path to the React app's data directory (relative from this script).
# The JS file is only written when this directory exists.
REACT_DATA_DIR = os.path.normpath(
    os.path.join(BASE_DIR, "..", "..", "code_Not_in_Use", "src", "data")
)
REACT_JS_FILE = os.path.join(REACT_DATA_DIR, "storeClusters.js")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LARGE_THRESHOLD = 500   # switch to BIRCH + PCA above this store count
MAX_K = 6               # cap on auto-detected cluster count

# Numeric features used for clustering.  Missing columns are silently skipped
# so the script works on partial datasets (e.g. 1000-store exports that lack
# a few optional columns).
NUMERIC_FEATURES = [
    "Store_Size_Sqft",
    "Population_5km",
    "Median_HH_Income_USD",
    "Traffic_Density_Score",
    "Footfall_Daily",
    "Competitor_Count_5km",
    "Distance_City_Center_KM",
    "Annual_Sales_Million",
    "Avg_Basket_Value",
    "Transactions_Daily",
    "Grocery_Sales_Pct",
    "Apparel_Sales_Pct",
    "Electronics_Sales_Pct",
    "Loyalty_Member_Pct",
    "Online_Order_Pct",
    "Population_Growth_Pct",
    "Distance_DC_KM",
]

# ---------------------------------------------------------------------------
# Business label rules (evaluated top-to-bottom; first match wins).
# Each entry: (predicate_fn, label, description)
# The predicate receives a stats dict with averaged cluster characteristics.
# ---------------------------------------------------------------------------
_LABEL_RULES = [
    (
        lambda s: s["pct_urban"] >= 0.6
        and s["avg_income"] >= 95_000
        and s["avg_basket"] >= 85,
        "Premium Urban",
        "High-income urban stores driving basket value and digital engagement.",
    ),
    (
        lambda s: s["pct_urban"] >= 0.5 and s["avg_online"] >= 26,
        "Digital-First Urban",
        "Urban stores with high online-order penetration and tech-savvy shoppers.",
    ),
    (
        lambda s: s["avg_pop_growth"] >= 3.8 and s["avg_income"] >= 85_000,
        "High-Growth Affluent",
        "Fast-growing catchments with above-average household incomes.",
    ),
    (
        lambda s: s["avg_income"] >= 80_000 and s["avg_sales"] >= 85,
        "Affluent Suburban",
        "Well-off suburban locations with steady footfall and high basket values.",
    ),
    (
        lambda s: s["pct_urban"] >= 0.4 and s["avg_income"] >= 72_000,
        "Established Metro",
        "Established metro-area stores with consistent mid-to-high performance.",
    ),
    (
        lambda s: s["pct_rural"] >= 0.5 and s["avg_distance"] >= 28,
        "Rural Remote",
        "Remote rural stores; supply-chain and logistics efficiency are key levers.",
    ),
    (
        lambda s: s["avg_footfall"] >= 4_000 and s["avg_basket"] < 76,
        "Value-Driven",
        "High-footfall, price-sensitive shoppers seeking everyday value.",
    ),
    (
        lambda s: s["avg_sales"] < 70 and s["avg_pop_growth"] >= 1.5,
        "Emerging Growth",
        "Smaller stores in growing markets with significant untapped revenue potential.",
    ),
    (
        lambda s: True,  # fallback — always matches
        "Community Local",
        "Community-serving stores with a loyal local customer base.",
    ),
]

# Badge colours assigned in order to cluster labels (for the React UI).
_BADGE_COLORS = [
    "#FFA500",  # orange  — top-tier
    "#1a2332",  # navy    — mid-tier
    "#28a745",  # green   — growing
    "#17a2b8",  # teal
    "#6f42c1",  # purple
    "#fd7e14",  # amber
]


# ---------------------------------------------------------------------------
# Step 1 – Load
# ---------------------------------------------------------------------------
def load_store_data(path=STORE_FILE):
    if _DB_AVAILABLE:
        df = _db_read("store_master", Path(path))
    elif os.path.isfile(path):
        df = pd.read_csv(path)
    else:
        raise FileNotFoundError(f"Store data file not found: {path}")
    if df.empty:
        raise ValueError(f"{path} is empty — nothing to cluster.")
    print(f"[load] {len(df)} stores loaded from {path}")
    return df


# ---------------------------------------------------------------------------
# Step 2 – Pre-process
# ---------------------------------------------------------------------------
def preprocess(df):
    """
    Select available numeric features, impute with column median, and
    StandardScale.  For large datasets, also reduce dimensions via PCA
    (keeping >= 95% explained variance) to speed up distance computations.
    """
    available = [c for c in NUMERIC_FEATURES if c in df.columns]
    if not available:
        raise ValueError(
            "No recognised numeric feature columns found. "
            f"Expected at least one of: {NUMERIC_FEATURES}"
        )

    X = df[available].copy()
    X = X.fillna(X.median(numeric_only=True))
    X_scaled = StandardScaler().fit_transform(X.values.astype(float))

    if len(df) > LARGE_THRESHOLD:
        from sklearn.decomposition import PCA

        pca = PCA(n_components=0.95, random_state=42)
        X_scaled = pca.fit_transform(X_scaled)
        print(
            f"[preprocess] PCA: {len(available)} features -> "
            f"{X_scaled.shape[1]} components (>= 95% variance retained)"
        )
    else:
        print(f"[preprocess] Using {len(available)} features: {available}")

    return X_scaled, available


# ---------------------------------------------------------------------------
# Step 3 – Cluster
# ---------------------------------------------------------------------------
def _auto_k(Z, max_k):
    """
    Estimate optimal k from the acceleration (second derivative) of the
    dendrogram merge distances.  A large acceleration signals that the next
    merge would combine genuinely distinct groups — the elbow in the tree.
    """
    last = Z[-max_k:, 2]          # merge distances for the last max_k steps
    accel = np.diff(last, 2)       # second finite difference
    k = int(accel[::-1].argmax()) + 2
    return max(2, min(k, max_k))


def run_clustering(X_scaled, n_clusters=None):
    """
    Ward hierarchical clustering with automatic k selection.

    Small datasets (n <= LARGE_THRESHOLD): direct scipy linkage.
    Large datasets (n > LARGE_THRESHOLD): BIRCH pre-clustering followed by
    Ward linkage on the sub-cluster centroids, then labels mapped back to all
    original rows.  This keeps memory at O(sqrt(n)^2) rather than O(n^2).
    """
    n = len(X_scaled)
    cap = min(MAX_K, n - 1)

    if n > LARGE_THRESHOLD:
        from sklearn.cluster import Birch

        n_sub = max((n_clusters or 4) * 8, int(n ** 0.5))
        print(f"[cluster] Large dataset — BIRCH pre-clustering to {n_sub} sub-groups")

        birch = Birch(n_clusters=n_sub, threshold=0.5)
        sub_labels = birch.fit_predict(X_scaled)
        unique_subs = np.unique(sub_labels)

        # Centroid of each BIRCH sub-cluster
        sub_centers = np.vstack(
            [X_scaled[sub_labels == s].mean(axis=0) for s in unique_subs]
        )
        Z = linkage(sub_centers, method="ward")
        k = n_clusters or _auto_k(Z, min(cap, len(sub_centers) - 1))
        sub_cluster_ids = fcluster(Z, k, criterion="maxclust") - 1

        # Map sub-cluster id -> final cluster id, then expand to all rows
        sub_to_cluster = {s: sub_cluster_ids[i] for i, s in enumerate(unique_subs)}
        labels = np.array([sub_to_cluster[s] for s in sub_labels])
    else:
        Z = linkage(X_scaled, method="ward")
        k = n_clusters or _auto_k(Z, cap)
        labels = fcluster(Z, k, criterion="maxclust") - 1

    print(f"[cluster] Ward hierarchical clustering -> k = {k}")
    return labels, k


# ---------------------------------------------------------------------------
# Step 4 – Business labels
# ---------------------------------------------------------------------------
def assign_business_labels(df, labels):
    """
    Derive a human-readable cluster label and rich metadata for each cluster
    by evaluating the _LABEL_RULES against aggregated cluster statistics.
    Clusters are ranked by a composite performance score (income + sales +
    footfall) so the top-performing cluster consistently earns the top label.
    """

    def _col_mean(grp, col):
        return float(grp[col].mean()) if col in grp.columns else 0.0

    def _col_pct(grp, col, val):
        return float((grp[col] == val).mean()) if col in grp.columns else 0.0

    df = df.copy()
    df["_cid"] = labels

    # Compute stats per cluster
    raw_stats = {}
    for cid in sorted(df["_cid"].unique()):
        g = df[df["_cid"] == cid]
        raw_stats[int(cid)] = {
            "avg_income": _col_mean(g, "Median_HH_Income_USD"),
            "avg_sales": _col_mean(g, "Annual_Sales_Million"),
            "avg_footfall": _col_mean(g, "Footfall_Daily"),
            "avg_basket": _col_mean(g, "Avg_Basket_Value"),
            "avg_online": _col_mean(g, "Online_Order_Pct"),
            "avg_pop_growth": _col_mean(g, "Population_Growth_Pct"),
            "avg_distance": _col_mean(g, "Distance_City_Center_KM"),
            "pct_urban": _col_pct(g, "Urban_Rural", "Urban"),
            "pct_rural": _col_pct(g, "Urban_Rural", "Rural"),
            "store_count": len(g),
            "stores": sorted(g["Store_ID"].tolist()) if "Store_ID" in g.columns else [],
        }

    # Rank clusters by composite performance (income + normalised sales + footfall)
    max_income = max(s["avg_income"] for s in raw_stats.values()) or 1
    max_sales = max(s["avg_sales"] for s in raw_stats.values()) or 1
    max_footfall = max(s["avg_footfall"] for s in raw_stats.values()) or 1

    def _composite(s):
        return (
            s["avg_income"] / max_income
            + s["avg_sales"] / max_sales
            + s["avg_footfall"] / max_footfall
        )

    ranked = sorted(raw_stats.keys(), key=lambda c: _composite(raw_stats[c]), reverse=True)

    # Assign labels in performance rank order so top cluster always gets
    # a premium label regardless of the raw cluster-id numbers.
    biz = {}
    for rank_pos, cid in enumerate(ranked):
        s = raw_stats[cid]
        label, desc = next(
            (lbl, dsc) for pred, lbl, dsc in _LABEL_RULES if pred(s)
        )
        biz[cid] = {
            "label": label,
            "description": desc,
            "rank": rank_pos,
            "store_count": s["store_count"],
            "stores": s["stores"],
            "avg_annual_sales_M": round(s["avg_sales"], 1),
            "avg_income_USD": int(round(s["avg_income"])),
            "avg_basket_value": round(s["avg_basket"], 1),
            "avg_footfall_daily": int(round(s["avg_footfall"])),
            "avg_online_pct": round(s["avg_online"], 1),
        }

    return biz


# ---------------------------------------------------------------------------
# Step 5 – Write outputs
# ---------------------------------------------------------------------------
def write_csv(df, labels, biz, path=CLUSTER_CSV):
    df_out = df[["Store_ID"]].copy() if "Store_ID" in df.columns else df.iloc[:, :1].copy()
    df_out.columns = ["Store_ID"]
    df_out["Cluster_ID"] = labels
    df_out["Cluster_Label"] = df_out["Cluster_ID"].map(lambda c: biz[c]["label"])
    df_out.to_csv(path, index=False)
    print(f"[output] CSV  -> {path}")
    return df_out


def write_json(biz, features, k, total_stores, path=CLUSTER_JSON):
    summary = {
        "num_clusters": k,
        "total_stores": total_stores,
        "features_used": features,
        "clusters": biz,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"[output] JSON -> {path}")


def write_react_js(biz, path=REACT_JS_FILE):
    """
    Emit an ES-module consumed by the React filter.

    CLUSTER_STORES  maps each cluster label (and "All Clusters") to the list
                    of Store_IDs it contains.
    CLUSTER_META    provides display metadata for each label.
    """
    out_dir = os.path.dirname(path)
    if not os.path.isdir(out_dir):
        print(f"[output] React data dir not found ({out_dir}) — skipping JS write.")
        return

    # Build CLUSTER_STORES dict
    cluster_stores = {"All Clusters": []}
    cluster_meta = {}
    for i, (cid, info) in enumerate(
        sorted(biz.items(), key=lambda kv: kv[1]["rank"])
    ):
        lbl = info["label"]
        stores = info["stores"]
        cluster_stores[lbl] = stores
        cluster_stores["All Clusters"] += stores
        cluster_meta[lbl] = {
            "description": info["description"],
            "avg_income_USD": info["avg_income_USD"],
            "avg_annual_sales_M": info["avg_annual_sales_M"],
            "avg_basket_value": info["avg_basket_value"],
            "avg_footfall_daily": info["avg_footfall_daily"],
            "avg_online_pct": info["avg_online_pct"],
            "badge_color": _BADGE_COLORS[i % len(_BADGE_COLORS)],
            "stores": stores,
        }

    js = (
        "// Auto-generated by cluster.py — do not edit manually.\n"
        "// Re-run cluster.py whenever Store_Master.csv changes.\n\n"
        f"export const CLUSTER_STORES = {json.dumps(cluster_stores, indent=2)};\n\n"
        f"export const CLUSTER_META = {json.dumps(cluster_meta, indent=2)};\n"
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    print(f"[output] JS   -> {path}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def run(store_path=None, output_csv=None, output_json=None, n_clusters=None):
    df = load_store_data(store_path or STORE_FILE)
    X_scaled, features = preprocess(df)
    labels, k = run_clustering(X_scaled, n_clusters)
    biz = assign_business_labels(df, labels)

    df_out = write_csv(df, labels, biz, output_csv or CLUSTER_CSV)
    write_json(biz, features, k, len(df), output_json or CLUSTER_JSON)
    write_react_js(biz)

    print("\n=== Cluster Summary ===")
    for cid, info in sorted(biz.items(), key=lambda kv: kv[1]["rank"]):
        print(
            f"  [{cid}] {info['label']:<22}  "
            f"stores={info['stores']}  "
            f"income=${info['avg_income_USD']:,}  "
            f"sales=${info['avg_annual_sales_M']}M"
        )

    return df_out, biz


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Hierarchical store clustering from Store_Master.csv"
    )
    parser.add_argument(
        "--store_file",
        default=STORE_FILE,
        help="Path to Store_Master.csv (default: same directory as this script)",
    )
    parser.add_argument(
        "--n_clusters",
        type=int,
        default=None,
        help="Force a specific number of clusters (default: auto-detect via dendrogram)",
    )
    parser.add_argument(
        "--output_csv",
        default=CLUSTER_CSV,
        help="Output path for store_clusters.csv",
    )
    parser.add_argument(
        "--output_json",
        default=CLUSTER_JSON,
        help="Output path for store_clusters_summary.json",
    )
    args = parser.parse_args()

    try:
        run(
            store_path=args.store_file,
            output_csv=args.output_csv,
            output_json=args.output_json,
            n_clusters=args.n_clusters,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
