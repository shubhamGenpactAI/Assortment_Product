"""
generate_market_data.py

Generates realistic synthetic retail market data for 60 Hair Care SKUs.
Reads  : Raw_Input/SKU_Master.csv
Outputs: Raw_Input/Market_Data.csv

Columns produced (in order):
  SKU_ID, SKU_Name, Dollar Sales, Unit Sales, Volume Sales, Dollar per Unit,
  Dollar Sales Growth %, Unit Sales Growth %, Market Share %, Share Change vs YA,
  Avg. Retail Price, Gross Margin %, % ACV Distribution, % Stores Selling,
  Velocity, Repeat Purchase Rate, Category Growth %, Distribution Trend,
  Incremental Sales Index

Design principles:
  - Seven performance profiles drive all metric ranges (top_seller, growth,
    stable, declining, niche, low_dist, delist).
  - Profiles are seeded from the analyst-assigned Status in SKU_Master plus
    launch year, so delist-candidate SKUs always land in the delist profile.
  - Dollar Sales is derived from Velocity × Stores Selling × 52 weeks, keeping
    distribution, velocity, and revenue internally consistent.
  - Market Share % and Share Change vs YA are computed post-generation from
    within-sub-category totals, guaranteeing they sum to 100 % per sub-cat.
  - Gross Margin uses SKU_Master Margin_Pct as a base, with small profile
    adjustments (growing SKUs defend margin; delist SKUs erode it).
"""

import pandas as pd
import numpy as np
from pathlib import Path

# ─────────────────────────── global config ───────────────────────────────────

SEED = 42
TOTAL_STORES = 500      # retail-universe store count used for distribution math
WEEKS = 52              # annual selling weeks

# Sub-category category-level growth rates (annual, decimal)
CATEGORY_GROWTH: dict[str, float] = {
    "Shampoo": 0.040,
    "Conditioner": 0.030,
    "Hair Color": 0.060,
    "Hair Mask": 0.080,
    "Hair Serum": 0.100,
    "Hair Oil": 0.050,
    "Treatment": 0.040,
}

# Retailer shelf price = list_price × markup (accounts for typical trade margin)
PRICE_MARKUP: dict[str, float] = {
    "Economy": 1.28,
    "Mainstream": 1.22,
    "Premium": 1.18,
}

# Base velocity ($/store selling/week) before profile multiplier
BASE_VELOCITY: dict[str, float] = {
    "Economy": 32.0,
    "Mainstream": 52.0,
    "Premium": 82.0,
}

# Sub-category ACV offset (percentage points added to the profile ACV midpoint)
# — broad formats like Shampoo/Conditioner distribute more widely than serums
SUBCATEGORY_ACV_OFFSET: dict[str, float] = {
    "Shampoo": 12.0,
    "Conditioner": 8.0,
    "Treatment": 5.0,
    "Hair Color": 0.0,
    "Hair Oil": -4.0,
    "Hair Mask": -8.0,
    "Hair Serum": -12.0,
}

# ─────────────────────── performance profile bands ───────────────────────────
# Each profile is a dict of (low, high) ranges or scalars used in generation.
# Keys:
#   acv          – % ACV Distribution range
#   vel_mult     – multiplier applied to BASE_VELOCITY to get $/store/week
#   sales_growth – Dollar Sales Growth % range (decimal)
#   unit_shift   – additive shift on sales growth to get unit growth (decimal)
#   repeat       – Repeat Purchase Rate range (decimal → %)
#   margin_adj   – additive adjustment to SKU_Master Margin_Pct (pp)
#   incr_idx     – Incremental Sales Index range
#   dist_trend   – default Distribution Trend label
#   stores_ratio – % Stores Selling = % ACV × this ratio (accounts for gaps)

PROFILES: dict[str, dict] = {
    "top_seller": dict(
        acv=(65, 92),
        vel_mult=(1.6, 3.2),
        sales_growth=(0.06, 0.22),
        unit_shift=(-0.02, 0.01),
        repeat=(0.45, 0.70),
        margin_adj=(2.0, 5.0),
        incr_idx=(112, 138),
        dist_trend="Growing",
        stores_ratio=(0.85, 0.97),
    ),
    "growth": dict(
        acv=(30, 65),
        vel_mult=(0.8, 1.8),
        sales_growth=(0.15, 0.45),
        unit_shift=(-0.03, 0.02),
        repeat=(0.22, 0.46),
        margin_adj=(0.0, 3.0),
        incr_idx=(104, 126),
        dist_trend="Growing",
        stores_ratio=(0.78, 0.93),
    ),
    "stable": dict(
        acv=(45, 76),
        vel_mult=(0.7, 1.4),
        sales_growth=(-0.03, 0.09),
        unit_shift=(-0.02, 0.01),
        repeat=(0.30, 0.56),
        margin_adj=(-1.0, 2.0),
        incr_idx=(94, 112),
        dist_trend="Stable",
        stores_ratio=(0.80, 0.95),
    ),
    "declining": dict(
        acv=(18, 55),
        vel_mult=(0.35, 0.88),
        sales_growth=(-0.24, -0.04),
        unit_shift=(-0.03, 0.01),
        repeat=(0.16, 0.38),
        margin_adj=(-4.0, 1.0),
        incr_idx=(77, 96),
        dist_trend="Declining",
        stores_ratio=(0.70, 0.88),
    ),
    "niche": dict(
        acv=(7, 28),
        vel_mult=(0.9, 2.0),          # high velocity within limited stores
        sales_growth=(-0.06, 0.30),
        unit_shift=(-0.02, 0.02),
        repeat=(0.42, 0.74),          # loyal niche buyers repurchase heavily
        margin_adj=(2.0, 9.0),
        incr_idx=(88, 108),
        dist_trend="Stable",
        stores_ratio=(0.83, 0.96),
    ),
    "low_dist": dict(
        acv=(5, 22),
        vel_mult=(0.25, 0.70),
        sales_growth=(0.10, 0.55),    # growing off a small base
        unit_shift=(-0.02, 0.02),
        repeat=(0.10, 0.32),
        margin_adj=(-2.0, 2.0),
        incr_idx=(80, 100),
        dist_trend="Growing",
        stores_ratio=(0.75, 0.92),
    ),
    "delist": dict(
        acv=(3, 16),
        vel_mult=(0.08, 0.30),
        sales_growth=(-0.52, -0.22),
        unit_shift=(-0.04, 0.01),
        repeat=(0.04, 0.18),
        margin_adj=(-6.0, -1.0),
        incr_idx=(50, 76),
        dist_trend="Declining",
        stores_ratio=(0.60, 0.82),
    ),
}


# ─────────────────────── profile assignment ──────────────────────────────────

def assign_profile(status: str, launch_year: int, rng: np.random.Generator) -> str:
    """
    Map SKU status + launch year to one of the seven performance profiles.

    Rules:
      - Delist Candidate  → always "delist"
      - Watch + new (≥2025) → 50% low_dist / 50% declining
      - Watch + older      → 60% declining / 25% niche / 15% stable
      - Active + new       → 50% growth / 30% low_dist / 20% stable
      - Active + older     → 20% top_seller / 55% stable / 25% growth
    """
    if status == "Delist Candidate":
        return "delist"

    is_new = launch_year >= 2025

    if status == "Watch":
        r = rng.random()
        if is_new:
            return "low_dist" if r < 0.50 else "declining"
        if r < 0.60:
            return "declining"
        if r < 0.85:
            return "niche"
        return "stable"

    # Active
    r = rng.random()
    if is_new:
        if r < 0.50:
            return "growth"
        if r < 0.80:
            return "low_dist"
        return "stable"

    # Established Active
    if r < 0.20:
        return "top_seller"
    if r < 0.75:
        return "stable"
    return "growth"


# ─────────────────────── per-SKU metric generation ───────────────────────────

def build_market_row(
    row: pd.Series,
    profile_name: str,
    rng: np.random.Generator,
) -> dict:
    """
    Generate all market metrics for a single SKU row from SKU_Master.
    Returns a flat dict ready for DataFrame construction.
    """
    p = PROFILES[profile_name]
    price_band  = str(row["Price_Band"])
    sub_cat     = str(row["Sub_Category"])
    base_margin = float(row["Margin_Pct"])
    list_price  = float(row["List_Price_USD"])
    pack_ml     = int(row["Pack_Size_ml"])

    # ── 1. Pricing ────────────────────────────────────────────────────────────
    markup = PRICE_MARKUP.get(price_band, 1.22)
    # Small ±4% noise on the standard markup (regional / retailer variation)
    avg_retail_price = round(list_price * markup * float(rng.uniform(0.96, 1.04)), 2)

    # Realized dollar per unit is slightly below shelf due to promotional depth
    promo_disc   = float(rng.uniform(0.90, 0.99))
    dollar_per_unit = round(avg_retail_price * promo_disc, 2)

    # ── 2. Distribution ───────────────────────────────────────────────────────
    acv_lo, acv_hi = p["acv"]
    # Apply sub-category ACV offset to widen/narrow the band naturally
    offset = SUBCATEGORY_ACV_OFFSET.get(sub_cat, 0.0)
    raw_acv = float(rng.uniform(acv_lo, acv_hi)) + offset * float(rng.uniform(0.6, 1.0))
    acv = round(float(np.clip(raw_acv, 2.0, 97.0)), 1)

    ratio_lo, ratio_hi = p["stores_ratio"]
    raw_stores_pct = acv * float(rng.uniform(ratio_lo, ratio_hi))
    stores_pct = round(float(np.clip(raw_stores_pct, 1.0, 98.0)), 1)
    stores_count = max(1, int(round(stores_pct / 100.0 * TOTAL_STORES)))

    # ── 3. Sales ──────────────────────────────────────────────────────────────
    base_vel = BASE_VELOCITY.get(price_band, 52.0)
    vel_lo, vel_hi = p["vel_mult"]
    velocity = round(float(base_vel * rng.uniform(vel_lo, vel_hi)), 2)

    # Dollar Sales = Velocity × Stores × 52 weeks (fundamental identity)
    dollar_sales = float(round(velocity * stores_count * WEEKS, 0))

    unit_sales = max(1, int(round(dollar_sales / dollar_per_unit)))

    # Volume Sales in litres (pack units × ml per unit / 1 000)
    volume_liters = round(unit_sales * pack_ml / 1000.0, 1)

    # ── 4. Growth ─────────────────────────────────────────────────────────────
    sg_lo, sg_hi = p["sales_growth"]
    dollar_sales_growth = round(float(rng.uniform(sg_lo, sg_hi)) * 100.0, 2)

    us_lo, us_hi = p["unit_shift"]
    # Unit growth ≈ dollar growth minus price inflation; shift captures that gap
    unit_sales_growth = round(
        (dollar_sales_growth / 100.0 + float(rng.uniform(us_lo, us_hi))) * 100.0, 2
    )

    # ── 5. Gross Margin ───────────────────────────────────────────────────────
    ma_lo, ma_hi = p["margin_adj"]
    raw_margin = base_margin + float(rng.uniform(ma_lo, ma_hi)) + float(rng.uniform(-1.5, 1.5))
    gross_margin = round(float(np.clip(raw_margin, 8.0, 58.0)), 2)

    # ── 6. Buyer behaviour ────────────────────────────────────────────────────
    rr_lo, rr_hi = p["repeat"]
    repeat_rate = round(float(rng.uniform(rr_lo, rr_hi)) * 100.0, 2)

    # ── 7. Category-level growth (sub-cat level with minor noise) ─────────────
    cat_base = CATEGORY_GROWTH.get(sub_cat, 0.045)
    category_growth = round((cat_base + float(rng.uniform(-0.008, 0.008))) * 100.0, 2)

    # ── 8. Incremental Sales Index ────────────────────────────────────────────
    ii_lo, ii_hi = p["incr_idx"]
    incr_idx = round(float(rng.uniform(ii_lo, ii_hi)), 1)

    # ── 9. Distribution Trend ─────────────────────────────────────────────────
    dist_trend = p["dist_trend"]
    # 8 % chance of a one-period deviation (seasonal gain/loss)
    if rng.random() < 0.08:
        options = [t for t in ["Growing", "Stable", "Declining"] if t != dist_trend]
        dist_trend = str(rng.choice(options))

    return {
        "SKU_ID":                   str(row["SKU_ID"]),
        "SKU_Name":                 str(row["Product_Name"]),
        "_sub_cat":                 sub_cat,          # temp — used for share calc
        "_sales_growth":            dollar_sales_growth,  # temp — used for share calc
        "Dollar Sales":             dollar_sales,
        "Unit Sales":               unit_sales,
        "Volume Sales":             volume_liters,
        "Dollar per Unit":          dollar_per_unit,
        "Dollar Sales Growth %":    dollar_sales_growth,
        "Unit Sales Growth %":      unit_sales_growth,
        "Avg. Retail Price":        avg_retail_price,
        "Gross Margin %":           gross_margin,
        "% ACV Distribution":       acv,
        "% Stores Selling":         stores_pct,
        "Velocity":                 velocity,
        "Repeat Purchase Rate":     repeat_rate,
        "Category Growth %":        category_growth,
        "Distribution Trend":       dist_trend,
        "Incremental Sales Index":  incr_idx,
    }


# ─────────────────────── post-generation share calculations ──────────────────

def compute_share_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute Market Share % and Share Change vs YA.

    Market Share % = SKU Dollar Sales / total sub-category Dollar Sales × 100
    Share Change   = current share − implied prior-year share, where
                     prior-year sales = current / (1 + growth_rate)
    """
    df = df.copy()

    # Current market share within sub-category
    subcat_total = df.groupby("_sub_cat")["Dollar Sales"].transform("sum")
    df["Market Share %"] = (df["Dollar Sales"] / subcat_total * 100.0).round(2)

    # Prior-year implied sales (guard against exact -100 % growth)
    safe_growth = df["_sales_growth"].clip(lower=-95.0)
    df["_prior_sales"] = df["Dollar Sales"] / (1.0 + safe_growth / 100.0)

    prior_subcat_total = df.groupby("_sub_cat")["_prior_sales"].transform("sum")
    df["_prior_share"]   = df["_prior_sales"] / prior_subcat_total * 100.0
    df["Share Change vs YA"] = (df["Market Share %"] - df["_prior_share"]).round(2)

    df = df.drop(columns=["_prior_sales", "_prior_share", "_sub_cat", "_sales_growth"])
    return df


# ─────────────────────── main orchestration ──────────────────────────────────

def main() -> None:
    project_root = Path(__file__).resolve().parent
    raw_input    = project_root / "Raw_Input"

    sku_master = pd.read_csv(raw_input / "SKU_Master.csv")
    print(f"Loaded {len(sku_master)} SKUs from SKU_Master.csv")

    rng = np.random.default_rng(SEED)

    # Step 1 — assign a performance profile to every SKU
    profiles: list[str] = []
    for _, row in sku_master.iterrows():
        try:
            launch_year = pd.to_datetime(row["Launch_Date"]).year
        except Exception:
            launch_year = 2023
        profiles.append(assign_profile(str(row["Status"]), launch_year, rng))
    sku_master["_profile"] = profiles

    # Step 2 — generate per-SKU market metrics
    records: list[dict] = []
    for _, row in sku_master.iterrows():
        records.append(build_market_row(row, str(row["_profile"]), rng))

    df = pd.DataFrame(records)

    # Step 3 — derive cross-SKU metrics (market share, share change)
    df = compute_share_metrics(df)

    # Step 4 — final column ordering as required
    final_cols = [
        "SKU_ID",
        "SKU_Name",
        "Dollar Sales",
        "Unit Sales",
        "Volume Sales",
        "Dollar per Unit",
        "Dollar Sales Growth %",
        "Unit Sales Growth %",
        "Market Share %",
        "Share Change vs YA",
        "Avg. Retail Price",
        "Gross Margin %",
        "% ACV Distribution",
        "% Stores Selling",
        "Velocity",
        "Repeat Purchase Rate",
        "Category Growth %",
        "Distribution Trend",
        "Incremental Sales Index",
    ]
    df = df[final_cols]

    out_path = raw_input / "Market_Data.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} rows to {out_path}\n")

    # ── summary diagnostics ──────────────────────────────────────────────────
    print("Profile distribution:")
    print(sku_master["_profile"].value_counts().to_string())

    print("\nDollar Sales range (USD):")
    print(f"  Min : ${df['Dollar Sales'].min():>12,.0f}")
    print(f"  Max : ${df['Dollar Sales'].max():>12,.0f}")
    print(f"  Mean: ${df['Dollar Sales'].mean():>12,.0f}")
    print(f"  Total category: ${df['Dollar Sales'].sum():>12,.0f}")

    print("\nACV Distribution range:")
    print(f"  Min: {df['% ACV Distribution'].min():.1f}%   "
          f"Max: {df['% ACV Distribution'].max():.1f}%   "
          f"Mean: {df['% ACV Distribution'].mean():.1f}%")

    print("\nGrowth % spread:")
    print(f"  Min: {df['Dollar Sales Growth %'].min():.1f}%   "
          f"Max: {df['Dollar Sales Growth %'].max():.1f}%   "
          f"Mean: {df['Dollar Sales Growth %'].mean():.1f}%")

    print("\nDistribution Trend counts:")
    print(df["Distribution Trend"].value_counts().to_string())

    print("\nSample rows:")
    print(
        df[["SKU_Name", "Dollar Sales", "Market Share %",
            "% ACV Distribution", "Velocity", "Dollar Sales Growth %"]]
        .head(10)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
