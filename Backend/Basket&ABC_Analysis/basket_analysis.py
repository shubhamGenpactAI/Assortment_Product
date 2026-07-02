"""
basket_analysis.py
==================
Market Basket Analysis and SKU Delisting Recommendation Module.

Inputs  (all must exist in the same directory as this script):
    Sales_Tx.csv      - Transaction line items; Txn_ID = basket, SKU_ID = item
    SKU_Master.csv    - SKU attribute enrichment (optional; warns if SKUs are absent)
    Store_Master.csv  - Store / geography attributes

Outputs (written to same directory):
    association_rules.csv          SKU-to-SKU rules with support, confidence, lift
    sku_basket_insights.csv        Per-SKU basket metrics (7 metrics)
    demand_transfer_matrix.csv     Within-sub-category demand transfer potential
    delisting_recommendations.csv  Delist scores + NL summary at 4 granularity levels

Run:
    python basket_analysis.py

Dependencies (already present in the project venv):
    pandas, numpy  — no additional installs required
"""

import itertools
import logging
import os
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
from db import get_engine
from sqlalchemy import text


# =============================================================================
# SECTION 1: CONFIGURATION
# =============================================================================

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
OUTPUTS_DIR  = os.path.join(PROJECT_ROOT, "Outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

# --- Output file paths ---
RULES_OUT    = os.path.join(OUTPUTS_DIR, "association_rules.csv")
INSIGHTS_OUT = os.path.join(OUTPUTS_DIR, "sku_basket_insights.csv")
TRANSFER_OUT = os.path.join(OUTPUTS_DIR, "demand_transfer_matrix.csv")
DELIST_OUT   = os.path.join(OUTPUTS_DIR, "delisting_recommendations.csv")

# --- Association rule parameters ---
# Minimum fraction of baskets a SKU must appear in to be included in rule mining.
# Filters out extremely rare SKUs that would produce unreliable statistics.
MIN_SUPPORT = 0.005  # 0.5% of total baskets

# --- Basket dependency threshold ---
# A co-purchased SKU Y is counted toward SKU X's dependency score only if
# confidence(X → Y) exceeds this threshold.
DEPENDENCY_CONFIDENCE_THRESHOLD = 0.10

# --- Substitution detection threshold ---
# Two SKUs in the same sub-category are treated as substitutes (rather than
# complements) when their co-purchase lift is below this value.
SUBSTITUTION_LIFT_THRESHOLD = 1.0

# --- Demand transfer: max substitute candidates to report per SKU ---
TOP_TRANSFER_N = 3

# --- Delist score weights (must sum to 1.0) ---
# Each component is normalised 0–1 where 1 = stronger case for delisting.
DELIST_WEIGHTS: Dict[str, float] = {
    "abc_signal":          0.15,  # C-class → high signal; A-class → low signal
    "revenue_signal":      0.20,  # low revenue rank → high signal
    "margin_signal":       0.20,  # low margin rank → high signal
    "support_signal":      0.15,  # low basket presence → high signal
    "lift_signal":         0.10,  # low avg lift → low basket integration
    "dependency_signal":   0.10,  # low dependency → safer to delist
    "substitution_signal": 0.10,  # high substitution availability → safer to delist
}
assert abs(sum(DELIST_WEIGHTS.values()) - 1.0) < 1e-9, "DELIST_WEIGHTS must sum to 1.0"

# --- Delist recommendation thresholds ---
DELIST_THRESHOLD = 0.65   # score >= this → "Recommend Delist"
WATCH_THRESHOLD  = 0.45   # score >= this → "Watch", else "Keep"

# --- ABC class → delist signal mapping ---
ABC_SIGNAL_MAP: Dict[str, float] = {"A": 0.0, "B": 0.5, "C": 1.0}

# --- Columns that MUST be present in Sales_Tx.csv (raises if missing) ---
REQUIRED_TX_COLS: List[str] = [
    "Txn_ID", "SKU_ID", "Store_ID", "Channel", "Geography",
    "ABC_Class", "Sub_Category",
    "Net_Sales_USD", "Gross_Margin_USD", "Promo_Flag",
]

# =============================================================================
# SECTION 2: LOGGING
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# =============================================================================
# SECTION 3: DATA LOADING & VALIDATION
# =============================================================================

def _check_required_columns(df: pd.DataFrame, required: List[str], file_label: str) -> None:
    """Raise a clear error if any required column is absent from the DataFrame."""
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(
            f"[{file_label}] Missing required columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )


def _read_table(table: str) -> pd.DataFrame:
    """Read an entire PostgreSQL table into a DataFrame."""
    with get_engine().connect() as conn:
        result = conn.execute(text(f'SELECT * FROM "{table}"'))
        return pd.DataFrame(result.fetchall(), columns=list(result.keys()))


def load_and_validate() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load sales_tx, sku_master, and store_master from PostgreSQL.

    Validation performed:
      - Required column presence check for sales_tx.
      - Numeric coercion with null-fill for financial columns.
      - Warning when SKUs in sales_tx are absent from sku_master (no hard failure
        because sales_tx itself carries the attributes needed for core analysis).

    Returns:
        tx           - cleaned transaction DataFrame
        sku_master   - SKU attribute master (may have fewer SKUs than tx; warned)
        store_master - Store master
    """
    tx           = _read_table("sales_tx")
    sku_master   = _read_table("sku_master")
    store_master = _read_table("store_master")

    log.info(f"Loaded sales_tx:      {len(tx):,} rows, {tx['Txn_ID'].nunique():,} unique baskets")
    log.info(f"Loaded sku_master:    {len(sku_master):,} rows")
    log.info(f"Loaded store_master:  {len(store_master):,} rows")

    if tx.empty:
        raise ValueError("sales_tx table is empty - cannot proceed.")

    # Required column check
    _check_required_columns(tx, REQUIRED_TX_COLS, "sales_tx")

    # Coerce financial and flag columns to numeric; fill nulls with 0
    for col in ["Net_Sales_USD", "Gross_Margin_USD", "Promo_Flag"]:
        tx[col] = pd.to_numeric(tx[col], errors="coerce")
        null_count = tx[col].isna().sum()
        if null_count > 0:
            log.warning(f"  {null_count:,} null values in '{col}' filled with 0.")
        tx[col] = tx[col].fillna(0)

    tx["Promo_Flag"] = tx["Promo_Flag"].astype(int)

    # Drop rows with null Txn_ID or SKU_ID — these cannot form a basket
    for key_col in ["Txn_ID", "SKU_ID"]:
        bad = tx[key_col].isna().sum()
        if bad > 0:
            log.warning(f"  Dropping {bad:,} rows with null {key_col}.")
    tx = tx.dropna(subset=["Txn_ID", "SKU_ID"]).reset_index(drop=True)

    # SKU coverage warning (soft — not a hard failure)
    tx_skus  = set(tx["SKU_ID"].unique())
    sku_skus = set(sku_master["SKU_ID"].unique()) if "SKU_ID" in sku_master.columns else set()
    uncovered = tx_skus - sku_skus
    if uncovered:
        log.warning(
            f"  {len(uncovered)} SKU(s) in sales_tx have no row in sku_master. "
            f"Core analysis will use attributes from sales_tx. "
            f"First 10 missing: {sorted(uncovered)[:10]}"
        )

    log.info(f"Unique SKUs in transactions: {len(tx_skus)}")
    return tx, sku_master, store_master


# =============================================================================
# SECTION 4: ASSOCIATION RULE MINING
# =============================================================================

def build_association_rules(
    tx: pd.DataFrame,
) -> Tuple[pd.DataFrame, Dict[str, float], int]:
    """
    Compute directed SKU-to-SKU association rules from transaction baskets.

    Algorithm (implemented from scratch — no external library):
      1. Group transaction lines by Txn_ID to obtain the set of SKUs per basket.
      2. Filter SKUs to those meeting MIN_SUPPORT (removes extremely rare items).
      3. For each unordered pair (A, B), count baskets that contain both.
      4. Derive support, confidence, and lift for both directions A→B and B→A.

    Formulas:
      support(A)      = baskets_with_A / total_baskets
      support(A,B)    = baskets_with_A_and_B / total_baskets
      confidence(A→B) = support(A,B) / support(A)
      lift(A→B)       = confidence(A→B) / support(B)
        lift > 1 → A and B co-occur more than by chance (complementary)
        lift < 1 → A and B co-occur less than by chance (substitutes)
        lift = 1 → independent

    Returns:
        rules          - DataFrame of directed rules
        item_support   - Dict mapping SKU_ID → support fraction
        total_baskets  - total number of unique baskets
    """
    log.info("-" * 50)
    log.info("STEP: Building association rules")

    # Build basket → frozenset(SKUs) mapping
    baskets_by_txn: Dict[str, set] = (
        tx.groupby("Txn_ID")["SKU_ID"]
          .apply(lambda x: set(x.unique()))
          .to_dict()
    )
    total_baskets = len(baskets_by_txn)
    log.info(f"  Total baskets: {total_baskets:,}")

    # Count baskets per SKU (item support numerator)
    sku_basket_count: Dict[str, int] = {}
    for basket_items in baskets_by_txn.values():
        for sku in basket_items:
            sku_basket_count[sku] = sku_basket_count.get(sku, 0) + 1

    item_support: Dict[str, float] = {
        sku: count / total_baskets for sku, count in sku_basket_count.items()
    }

    # Filter to SKUs meeting minimum support
    valid_skus = {sku for sku, sup in item_support.items() if sup >= MIN_SUPPORT}
    log.info(f"  SKUs meeting min_support >= {MIN_SUPPORT}: {len(valid_skus)} of {len(item_support)}")

    if len(valid_skus) < 2:
        log.warning("  Fewer than 2 valid SKUs - no pairs can be formed. Returning empty rules.")
        return pd.DataFrame(), item_support, total_baskets

    # Count co-occurrences for all valid SKU pairs
    pair_count: Dict[Tuple[str, str], int] = {}
    for basket_items in baskets_by_txn.values():
        valid_in_basket = sorted(set(basket_items) & valid_skus)
        if len(valid_in_basket) < 2:
            continue
        for a, b in itertools.combinations(valid_in_basket, 2):
            pair_count[(a, b)] = pair_count.get((a, b), 0) + 1

    log.info(f"  Unique co-occurring SKU pairs found: {len(pair_count):,}")

    # Build directed rules for both A→B and B→A from each unordered pair
    rows: List[dict] = []
    for (a, b), co_count in pair_count.items():
        sup_ab = co_count / total_baskets
        sup_a  = item_support[a]
        sup_b  = item_support[b]

        conf_ab = sup_ab / sup_a if sup_a > 0 else 0.0
        conf_ba = sup_ab / sup_b if sup_b > 0 else 0.0
        lift_ab = conf_ab / sup_b if sup_b > 0 else 0.0
        lift_ba = conf_ba / sup_a if sup_a > 0 else 0.0

        for ant, con, conf, lift, sup_ant, sup_con in [
            (a, b, conf_ab, lift_ab, sup_a, sup_b),
            (b, a, conf_ba, lift_ba, sup_b, sup_a),
        ]:
            rows.append({
                "antecedent_sku":       ant,
                "consequent_sku":       con,
                "support_antecedent":   round(sup_ant, 6),
                "support_consequent":   round(sup_con, 6),
                "support_pair":         round(sup_ab,  6),
                "confidence":           round(conf,    6),
                "lift":                 round(lift,    6),
                "co_occurrence_count":  co_count,
            })

    rules = (
        pd.DataFrame(rows)
          .sort_values(["antecedent_sku", "lift"], ascending=[True, False])
          .reset_index(drop=True)
    )
    log.info(f"  Directed association rules generated: {len(rules):,}")
    return rules, item_support, total_baskets


# =============================================================================
# SECTION 5: SKU BASKET INSIGHTS
# =============================================================================

def _avg_basket_revenue_excl_focal(
    basket_ids: set,
    focal_sku: str,
    tx: pd.DataFrame,
    basket_revenue_index: pd.Series,
) -> Optional[float]:
    """
    For a given set of basket IDs, compute the mean revenue of all line items
    EXCLUDING the focal SKU. Returns None if basket_ids is empty.
    """
    if not basket_ids:
        return None
    basket_list = list(basket_ids)

    # Revenue attributable to the focal SKU in each basket
    focal_rev = (
        tx[(tx["SKU_ID"] == focal_sku) & (tx["Txn_ID"].isin(basket_ids))]
        .groupby("Txn_ID")["Net_Sales_USD"]
        .sum()
        .reindex(basket_list, fill_value=0)
    )
    total_rev = basket_revenue_index.reindex(basket_list, fill_value=0)
    other_rev = (total_rev - focal_rev).clip(lower=0)
    return float(other_rev.mean())


def compute_sku_basket_insights(
    tx: pd.DataFrame,
    rules: pd.DataFrame,
    item_support: Dict[str, float],
    sku_master: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute 7 basket-level metrics for every SKU observed in Sales_Tx.csv.

    Metric definitions
    ------------------
    basket_revenue_impact
        Average total basket revenue (all items) for baskets containing this SKU,
        minus the overall average basket revenue. Positive = baskets with this SKU
        are worth more than average.

    basket_margin_impact
        Same as above but for Gross_Margin_USD.

    basket_dependency_score
        Count of OTHER SKUs for which confidence(this_SKU → other) > threshold.
        High score = this SKU is an "anchor" that pulls many others into the basket.

    substitution_score
        Fraction of same-sub-category peers where lift(this_SKU, peer) < 1.
        High score = many substitutes exist; low score = this SKU is unique in its niche.

    demand_transfer_candidates
        Top-N same-sub-category SKUs with lift < 1 (substitutes), ranked by
        their own basket support (availability). Semicolon-separated.

    promo_halo_impact
        When this SKU carries Promo_Flag = 1, the mean revenue of ALL OTHER items
        in the basket minus that same metric when Promo_Flag = 0.
        Positive = promotions on this SKU drive incremental spend on other items.

    cross_category_relationships
        Sub-categories (other than this SKU's own) that appear alongside this SKU
        in at least one basket, with co-occurrence counts. Format: "SubCat:count".

    Returns:
        DataFrame with one row per SKU.
    """
    log.info("-" * 50)
    log.info("STEP: Computing SKU basket insights")

    # Pre-compute basket-level revenue and margin totals for fast lookup
    basket_totals = (
        tx.groupby("Txn_ID")
          .agg(basket_revenue=("Net_Sales_USD", "sum"),
               basket_margin=("Gross_Margin_USD", "sum"))
    )
    basket_revenue_index = basket_totals["basket_revenue"]
    basket_margin_index  = basket_totals["basket_margin"]

    global_avg_basket_revenue = float(basket_revenue_index.mean())
    global_avg_basket_margin  = float(basket_margin_index.mean())

    # SKU → sub-category (majority vote across tx rows)
    sku_subcat: Dict[str, str] = (
        tx.groupby("SKU_ID")["Sub_Category"]
          .agg(lambda x: x.mode().iloc[0])
          .to_dict()
    )

    # Build basket → set of sub-categories (for cross-category computation)
    basket_subcat_sets: Dict[str, set] = (
        tx.groupby("Txn_ID")["Sub_Category"]
          .apply(set)
          .to_dict()
    )

    # Pre-process rules into lookup dicts for efficiency
    has_rules = len(rules) > 0
    if has_rules:
        rules_enriched = rules.copy()
        rules_enriched["antecedent_subcat"] = rules_enriched["antecedent_sku"].map(sku_subcat)
        rules_enriched["consequent_subcat"]  = rules_enriched["consequent_sku"].map(sku_subcat)
        # Group by antecedent for fast per-SKU lookup
        rules_by_ant: Dict[str, pd.DataFrame] = {
            ant: grp for ant, grp in rules_enriched.groupby("antecedent_sku")
        }
    else:
        rules_by_ant = {}

    # Build basket membership per SKU for promo halo computation
    txn_sku_promo = tx[["Txn_ID", "SKU_ID", "Promo_Flag"]].copy()

    all_skus = sorted(tx["SKU_ID"].unique())
    rows: List[dict] = []

    for sku_id in all_skus:
        sku_tx = tx[tx["SKU_ID"] == sku_id]
        sku_baskets = set(sku_tx["Txn_ID"].unique())
        n_sku_baskets = len(sku_baskets)

        if n_sku_baskets == 0:
            continue

        sku_sub = sku_subcat.get(sku_id, "Unknown")

        # 1. basket_revenue_impact
        avg_rev_with_sku = float(basket_revenue_index.reindex(list(sku_baskets)).mean())
        basket_revenue_impact = round(avg_rev_with_sku - global_avg_basket_revenue, 4)

        # 2. basket_margin_impact
        avg_marg_with_sku = float(basket_margin_index.reindex(list(sku_baskets)).mean())
        basket_margin_impact = round(avg_marg_with_sku - global_avg_basket_margin, 4)

        # 3. basket_dependency_score
        sku_rules_out = rules_by_ant.get(sku_id, pd.DataFrame())
        if not sku_rules_out.empty:
            basket_dependency_score = int(
                (sku_rules_out["confidence"] > DEPENDENCY_CONFIDENCE_THRESHOLD).sum()
            )
        else:
            basket_dependency_score = 0

        # 4 & 5. substitution_score and demand_transfer_candidates
        if not sku_rules_out.empty:
            same_subcat_rules = sku_rules_out[
                sku_rules_out["consequent_subcat"] == sku_sub
            ]
            n_peers = len(same_subcat_rules)
            if n_peers > 0:
                subst_mask = same_subcat_rules["lift"] < SUBSTITUTION_LIFT_THRESHOLD
                substitution_score = round(float(subst_mask.sum()) / n_peers, 4)
                transfer_candidates = (
                    same_subcat_rules[subst_mask]
                    .sort_values("support_consequent", ascending=False)
                    .head(TOP_TRANSFER_N)["consequent_sku"]
                    .tolist()
                )
            else:
                substitution_score     = 0.0
                transfer_candidates    = []
        else:
            substitution_score  = 0.0
            transfer_candidates = []

        demand_transfer_str = "; ".join(transfer_candidates) if transfer_candidates else "None"

        # 6. promo_halo_impact
        promo_txns   = set(txn_sku_promo[(txn_sku_promo["SKU_ID"] == sku_id) & (txn_sku_promo["Promo_Flag"] == 1)]["Txn_ID"])
        nopromo_txns = set(txn_sku_promo[(txn_sku_promo["SKU_ID"] == sku_id) & (txn_sku_promo["Promo_Flag"] == 0)]["Txn_ID"])

        rev_promo   = _avg_basket_revenue_excl_focal(promo_txns,   sku_id, tx, basket_revenue_index)
        rev_nopromo = _avg_basket_revenue_excl_focal(nopromo_txns, sku_id, tx, basket_revenue_index)

        if rev_promo is not None and rev_nopromo is not None:
            promo_halo_impact = round(rev_promo - rev_nopromo, 4)
        elif rev_promo is not None:
            promo_halo_impact = round(rev_promo, 4)   # no no-promo baseline
        else:
            promo_halo_impact = None  # SKU never appeared (should not happen)

        # 7. cross_category_relationships
        cross_counts: Dict[str, int] = {}
        for txn_id in sku_baskets:
            for sc in basket_subcat_sets.get(txn_id, set()):
                if sc != sku_sub:
                    cross_counts[sc] = cross_counts.get(sc, 0) + 1

        cross_category_str = "; ".join(
            f"{sc}:{cnt}"
            for sc, cnt in sorted(cross_counts.items(), key=lambda x: -x[1])
        ) if cross_counts else "None"

        rows.append({
            "SKU_ID":                       sku_id,
            "Sub_Category":                 sku_sub,
            "n_baskets_present":            n_sku_baskets,
            "support":                      round(item_support.get(sku_id, 0), 6),
            "basket_revenue_impact":        basket_revenue_impact,
            "basket_margin_impact":         basket_margin_impact,
            "basket_dependency_score":      basket_dependency_score,
            "substitution_score":           substitution_score,
            "demand_transfer_candidates":   demand_transfer_str,
            "promo_halo_impact":            promo_halo_impact,
            "cross_category_relationships": cross_category_str,
        })

    insights = pd.DataFrame(rows).sort_values("SKU_ID").reset_index(drop=True)
    log.info(f"  Basket insights computed for {len(insights)} SKUs.")
    return insights


# =============================================================================
# SECTION 6: DEMAND TRANSFER MATRIX
# =============================================================================

def compute_demand_transfer_matrix(
    tx: pd.DataFrame,
    rules: pd.DataFrame,
    sku_master: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build a demand transfer matrix for within-sub-category SKU pairs.

    For each pair (A → B) in the same Sub_Category:
      transfer_confidence  = confidence(A → B)
          Interpretation: of all baskets that contained SKU A, this fraction
          also contained SKU B. If A is delisted, B already has this share of
          A's customer base.
      revenue_ratio_B_over_A
          B's total revenue / A's total revenue.
          Values > 1 mean B is larger; values < 1 mean B is smaller.

    Long-format output: one row per directed within-sub-category pair.

    Returns:
        DataFrame with one row per (from_sku, to_sku) same-sub-category pair.
    """
    log.info("-" * 50)
    log.info("STEP: Computing demand transfer matrix")

    if rules.empty:
        log.warning("  Rules DataFrame is empty - transfer matrix will be empty.")
        return pd.DataFrame()

    # SKU total revenue and sub-category
    sku_revenue: Dict[str, float] = tx.groupby("SKU_ID")["Net_Sales_USD"].sum().to_dict()
    sku_subcat: Dict[str, str]    = (
        tx.groupby("SKU_ID")["Sub_Category"]
          .agg(lambda x: x.mode().iloc[0])
          .to_dict()
    )

    # SKU status from master (optional enrichment)
    sku_status: Dict[str, str] = {}
    if "SKU_ID" in sku_master.columns and "Status" in sku_master.columns:
        sku_status = sku_master.set_index("SKU_ID")["Status"].to_dict()

    # Enrich rules with sub-category
    rules_enriched = rules.copy()
    rules_enriched["antecedent_subcat"] = rules_enriched["antecedent_sku"].map(sku_subcat)
    rules_enriched["consequent_subcat"]  = rules_enriched["consequent_sku"].map(sku_subcat)

    # Retain only same-sub-category pairs
    same_subcat = rules_enriched[
        rules_enriched["antecedent_subcat"] == rules_enriched["consequent_subcat"]
    ].copy()

    rows: List[dict] = []
    for _, row in same_subcat.iterrows():
        a, b = row["antecedent_sku"], row["consequent_sku"]
        rev_a = sku_revenue.get(a, 0)
        rev_b = sku_revenue.get(b, 0)
        revenue_ratio = round(rev_b / rev_a, 4) if rev_a > 0 else None

        rows.append({
            "from_sku":                a,
            "to_sku":                  b,
            "sub_category":            row["antecedent_subcat"],
            "transfer_confidence":     row["confidence"],
            "transfer_lift":           row["lift"],
            "support_pair":            row["support_pair"],
            "from_sku_total_revenue":  round(rev_a, 2),
            "to_sku_total_revenue":    round(rev_b, 2),
            "revenue_ratio_B_over_A":  revenue_ratio,
            "from_sku_status":         sku_status.get(a, "Unknown"),
            "to_sku_status":           sku_status.get(b, "Unknown"),
        })

    transfer = (
        pd.DataFrame(rows)
          .sort_values(["from_sku", "transfer_confidence"], ascending=[True, False])
          .reset_index(drop=True)
    )
    log.info(f"  Demand transfer matrix rows: {len(transfer):,}")
    return transfer


# =============================================================================
# SECTION 7: DELIST SCORING
# =============================================================================

def _percentile_rank_dict(series: pd.Series) -> Dict:
    """
    Return a dict mapping index → percentile rank (0–1) for a pandas Series.
    Higher value in the series → higher rank (closer to 1.0).
    Uses 'average' method so tied values receive the same rank.
    """
    return series.rank(pct=True, method="average").to_dict()


def _abc_to_signal(abc_class: str) -> float:
    """Map an ABC class string to its delist signal (0 = keep, 1 = delist)."""
    return ABC_SIGNAL_MAP.get(str(abc_class).strip().upper(), 0.5)


def _make_delist_rows(
    group_tx: pd.DataFrame,
    level: str,
    value: str,
    avg_lift_global: Dict[str, float],
    dependency_map: Dict[str, int],
    sub_score_map: Dict[str, float],
    sku_abc: Dict[str, str],
    sku_subcat: Dict[str, str],
) -> List[dict]:
    """
    Compute delist scores for all SKUs present in group_tx.

    All percentile ranks are computed WITHIN the group so scores reflect
    relative performance at that granularity (store / geography / channel).

    Parameters
    ----------
    group_tx       : Filtered slice of Sales_Tx for this granularity group.
    level          : "Global" / "Store" / "Geography" / "Channel"
    value          : The specific value, e.g. "ST01" / "APAC" / "Online"
    avg_lift_global: Pre-computed global average lift per SKU (from association rules).
    dependency_map : basket_dependency_score per SKU (global, from insights).
    sub_score_map  : substitution_score per SKU (global, from insights).
    sku_abc        : ABC_Class per SKU (modal value from full tx).
    sku_subcat     : Sub_Category per SKU.
    """
    if group_tx.empty:
        return []

    all_skus = list(group_tx["SKU_ID"].unique())

    # Revenue and margin per SKU in this group
    sku_rev_s  = group_tx.groupby("SKU_ID")["Net_Sales_USD"].sum()
    sku_marg_s = group_tx.groupby("SKU_ID")["Gross_Margin_USD"].sum()

    # Basket-level support in this group
    group_basket_sets = (
        group_tx.groupby("Txn_ID")["SKU_ID"].apply(set)
    )
    total_group_baskets = len(group_basket_sets)
    grp_support_count: Dict[str, int] = {}
    for basket in group_basket_sets:
        for s in basket:
            grp_support_count[s] = grp_support_count.get(s, 0) + 1
    grp_support: Dict[str, float] = {
        s: c / total_group_baskets for s, c in grp_support_count.items()
    }

    # Build Series for ranking (indexed by SKU, limited to SKUs in this group)
    sup_series  = pd.Series({s: grp_support.get(s, 0)          for s in all_skus})
    lift_series = pd.Series({s: avg_lift_global.get(s, 1.0)    for s in all_skus})
    dep_series  = pd.Series({s: float(dependency_map.get(s, 0)) for s in all_skus})
    sub_series  = pd.Series({s: sub_score_map.get(s, 0.0)       for s in all_skus})

    # Percentile rank dicts (higher value in original series → rank closer to 1)
    rev_rank  = _percentile_rank_dict(sku_rev_s)
    marg_rank = _percentile_rank_dict(sku_marg_s)
    sup_rank  = _percentile_rank_dict(sup_series)
    lift_rank = _percentile_rank_dict(lift_series)
    dep_rank  = _percentile_rank_dict(dep_series)
    sub_rank  = _percentile_rank_dict(sub_series)

    rows_out: List[dict] = []
    for sku_id in all_skus:
        abc_cls = sku_abc.get(sku_id, "B")
        abc_sig = _abc_to_signal(abc_cls)

        # For revenue/margin/support/lift: low value = high delist signal → use (1 - rank)
        rev_sig  = 1.0 - rev_rank.get(sku_id, 0.5)
        marg_sig = 1.0 - marg_rank.get(sku_id, 0.5)
        sup_sig  = 1.0 - sup_rank.get(sku_id, 0.5)
        lift_sig = 1.0 - lift_rank.get(sku_id, 0.5)

        # Dependency: low dependency = safer to delist = high delist signal → (1 - rank)
        dep_sig  = 1.0 - dep_rank.get(sku_id, 0.5)

        # Substitution: high substitution available = safer to delist = high signal → rank as-is
        sub_sig  = sub_rank.get(sku_id, 0.5)

        delist_score = (
            DELIST_WEIGHTS["abc_signal"]          * abc_sig  +
            DELIST_WEIGHTS["revenue_signal"]       * rev_sig  +
            DELIST_WEIGHTS["margin_signal"]        * marg_sig +
            DELIST_WEIGHTS["support_signal"]       * sup_sig  +
            DELIST_WEIGHTS["lift_signal"]          * lift_sig +
            DELIST_WEIGHTS["dependency_signal"]    * dep_sig  +
            DELIST_WEIGHTS["substitution_signal"]  * sub_sig
        )
        delist_score = round(min(max(delist_score, 0.0), 1.0), 4)

        if delist_score >= DELIST_THRESHOLD:
            recommendation = "Recommend Delist"
        elif delist_score >= WATCH_THRESHOLD:
            recommendation = "Watch"
        else:
            recommendation = "Keep"

        rows_out.append({
            "SKU_ID":                  sku_id,
            "Sub_Category":            sku_subcat.get(sku_id, "Unknown"),
            "ABC_Class":               abc_cls,
            "granularity_level":       level,
            "granularity_value":       value,
            "total_revenue":           round(float(sku_rev_s.get(sku_id,  0)), 2),
            "total_margin":            round(float(sku_marg_s.get(sku_id, 0)), 2),
            "support_in_group":        round(grp_support.get(sku_id, 0), 6),
            "avg_lift":                round(avg_lift_global.get(sku_id, 1.0), 4),
            "basket_dependency_score": dependency_map.get(sku_id, 0),
            "substitution_score":      round(sub_score_map.get(sku_id, 0.0), 4),
            # Individual signals (for audit / explainability)
            "abc_signal":              round(abc_sig,  4),
            "revenue_signal":          round(rev_sig,  4),
            "margin_signal":           round(marg_sig, 4),
            "support_signal":          round(sup_sig,  4),
            "lift_signal":             round(lift_sig, 4),
            "dependency_signal":       round(dep_sig,  4),
            "substitution_signal":     round(sub_sig,  4),
            "delist_score":            delist_score,
            "recommendation":          recommendation,
        })

    return rows_out


def compute_delist_scores(
    tx: pd.DataFrame,
    insights: pd.DataFrame,
    rules: pd.DataFrame,
    sku_master: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute delist recommendations at four granularity levels:
      - Global     (all stores, all channels, all geographies)
      - Store      (one entry per Store_ID × SKU_ID)
      - Geography  (one entry per Geography × SKU_ID)
      - Channel    (one entry per Channel × SKU_ID)

    Scores are percentile-ranked WITHIN each group so they reflect relative
    performance at that level, not globally. A SKU that is C-class globally
    may still be a critical performer within a specific region.

    Returns:
        Long-format DataFrame with one row per (granularity_level, granularity_value, SKU_ID).
    """
    log.info("-" * 50)
    log.info("STEP: Computing delist scores at all granularity levels")

    # Pre-compute global average lift per SKU (antecedent) from association rules
    if not rules.empty:
        avg_lift_global: Dict[str, float] = (
            rules.groupby("antecedent_sku")["lift"].mean().to_dict()
        )
    else:
        avg_lift_global = {}

    # Load insight maps (global — used as-is across all granularity levels)
    dependency_map: Dict[str, int]   = insights.set_index("SKU_ID")["basket_dependency_score"].to_dict()
    sub_score_map:  Dict[str, float] = insights.set_index("SKU_ID")["substitution_score"].to_dict()

    # ABC class and sub-category (modal value per SKU from full tx)
    sku_abc:    Dict[str, str] = tx.groupby("SKU_ID")["ABC_Class"].agg(lambda x: x.mode().iloc[0]).to_dict()
    sku_subcat: Dict[str, str] = tx.groupby("SKU_ID")["Sub_Category"].agg(lambda x: x.mode().iloc[0]).to_dict()

    # Shared kwargs for _make_delist_rows
    shared_kwargs = dict(
        avg_lift_global=avg_lift_global,
        dependency_map=dependency_map,
        sub_score_map=sub_score_map,
        sku_abc=sku_abc,
        sku_subcat=sku_subcat,
    )

    all_rows: List[dict] = []

    # --- Global ---
    all_rows.extend(_make_delist_rows(tx, "Global", "Global", **shared_kwargs))
    log.info("  Global level: done")

    # --- Store ---
    for store_id, grp in tx.groupby("Store_ID"):
        all_rows.extend(_make_delist_rows(grp, "Store", str(store_id), **shared_kwargs))
    log.info(f"  Store level: {tx['Store_ID'].nunique()} stores done")

    # --- Geography ---
    for geo, grp in tx.groupby("Geography"):
        all_rows.extend(_make_delist_rows(grp, "Geography", str(geo), **shared_kwargs))
    log.info(f"  Geography level: {tx['Geography'].nunique()} geographies done")

    # --- Channel ---
    for ch, grp in tx.groupby("Channel"):
        all_rows.extend(_make_delist_rows(grp, "Channel", str(ch), **shared_kwargs))
    log.info(f"  Channel level: {tx['Channel'].nunique()} channels done")

    delist_df = (
        pd.DataFrame(all_rows)
          .sort_values(
              ["granularity_level", "granularity_value", "delist_score"],
              ascending=[True, True, False],
          )
          .reset_index(drop=True)
    )
    log.info(f"  Total delist recommendation rows: {len(delist_df):,}")
    return delist_df


# =============================================================================
# SECTION 8: NATURAL LANGUAGE SUMMARY
# =============================================================================

def generate_nl_summary(
    delist_df: pd.DataFrame,
    sku_master: pd.DataFrame,
) -> pd.DataFrame:
    """
    Append a concise, template-driven natural language summary to every row
    of the delist recommendations DataFrame.

    The summary is generated purely from computed values — no assumptions are
    made about what the numbers mean beyond what the formulas define. Each
    sentence maps directly to one of the seven delist score components.

    Returns:
        delist_df with an additional 'nl_summary' column.
    """
    log.info("-" * 50)
    log.info("STEP: Generating natural language summaries")

    # Optional product name lookup from SKU_Master
    sku_names: Dict[str, str] = {}
    if not sku_master.empty and "SKU_ID" in sku_master.columns and "Product_Name" in sku_master.columns:
        sku_names = sku_master.set_index("SKU_ID")["Product_Name"].to_dict()

    recommendation_rationale = {
        "Recommend Delist": (
            "Low revenue and/or margin contribution, limited basket presence, "
            "and sufficient substitutes collectively support a delisting decision."
        ),
        "Watch": (
            "Mixed performance signals - further monitoring is advised before "
            "making a final delisting call."
        ),
        "Keep": (
            "Strong revenue, margin, or basket integration argues for retaining "
            "this SKU in the current assortment."
        ),
    }

    def _build_summary(row: pd.Series) -> str:
        sku    = row["SKU_ID"]
        name   = sku_names.get(sku, sku)
        abc    = row["ABC_Class"]
        subcat = row["Sub_Category"]
        level  = row["granularity_level"]
        value  = row["granularity_value"]
        rev    = row["total_revenue"]
        marg   = row["total_margin"]
        score  = row["delist_score"]
        rec    = row["recommendation"]
        sup    = row["support_in_group"]
        dep    = int(row["basket_dependency_score"])
        sub_s  = float(row["substitution_score"])
        lift   = row["avg_lift"]

        scope = "globally" if level == "Global" else f"at {level} level ('{value}')"

        # Basket dependency sentence
        if dep >= 5:
            dep_comment = (
                f"It has a HIGH basket dependency score ({dep}), meaning it frequently "
                "co-anchors other SKUs - delisting carries disruption risk."
            )
        elif dep >= 2:
            dep_comment = f"It has a MODERATE basket dependency score ({dep})."
        else:
            dep_comment = (
                f"Its basket dependency score is LOW ({dep}), so delisting is unlikely "
                "to disrupt other SKUs' co-purchase patterns."
            )

        # Substitution sentence
        if sub_s >= 0.5:
            sub_comment = (
                f"Substitution availability is HIGH ({sub_s:.0%} of same-sub-category "
                "peers are potential alternatives), supporting a safer delist."
            )
        elif sub_s > 0:
            sub_comment = (
                f"Substitution availability is MODERATE ({sub_s:.0%} of same-sub-category "
                "peers qualify as alternatives)."
            )
        else:
            sub_comment = (
                "No same-sub-category substitutes were identified in the basket data - "
                "delisting may leave a gap in the assortment."
            )

        rationale = recommendation_rationale.get(rec, "")

        return (
            f"{sku} ('{name}') is an {abc}-class SKU in {subcat}. "
            f"Evaluated {scope}, it generated ${rev:,.2f} in revenue and "
            f"${marg:,.2f} in gross margin. "
            f"It appeared in {sup:.1%} of baskets with an average co-purchase "
            f"lift of {lift:.2f}. "
            f"{dep_comment} "
            f"{sub_comment} "
            f"Composite delist score: {score:.2f} - Recommendation: {rec}. "
            f"{rationale}"
        )

    delist_df = delist_df.copy()
    delist_df["nl_summary"] = delist_df.apply(_build_summary, axis=1)
    log.info(f"  NL summaries generated for {len(delist_df):,} rows.")
    return delist_df


# =============================================================================
# SECTION 9: ENHANCED KPI ENRICHMENT
# =============================================================================
# Adds 12 new columns to delist_recommendations.csv:
#   SalesIndex, MarginIndex, VelocityIndex, InventoryEfficiency,
#   SentimentIndex, MarketStrengthIndex, Health_Score, GMROI,
#   Forecasted_Sales, Forecast_Growth_Pct, Trend_Direction, Forecast_Confidence
# All existing columns and delist_score logic are preserved untouched.
# =============================================================================


def _safe_div(numerator: pd.Series, denominator: pd.Series,
               fill: float = np.nan) -> pd.Series:
    """Element-wise division with zero/null denominator protection."""
    return numerator.where(denominator.abs() > 1e-9, fill) / denominator.where(
        denominator.abs() > 1e-9, np.nan
    )


def _min_max_norm(series: pd.Series) -> pd.Series:
    """Min-max normalize to [0, 1]; returns 0.5 for constant series."""
    lo, hi = series.min(), series.max()
    if hi > lo:
        return (series - lo) / (hi - lo)
    return pd.Series(0.5, index=series.index, dtype=float)


def load_supplemental_data() -> Tuple[pd.DataFrame, pd.DataFrame,
                                       pd.DataFrame, pd.DataFrame]:
    """
    Load the four supplemental tables from PostgreSQL needed for enhanced KPI computation.
    Each table failure is logged as a warning and returns an empty DataFrame
    so the rest of the pipeline continues with NaN values for that metric.

    Returns: (inventory_df, reviews_df, market_data_df, forecast_df)
    """
    def _try_read_table(table: str, label: str) -> pd.DataFrame:
        try:
            df = _read_table(table)
            log.info(f"  Loaded {label}: {len(df):,} rows")
            return df
        except Exception as exc:
            log.warning(f"  Table not found or unreadable, skipping: {label} -> {exc}")
            return pd.DataFrame()

    inv      = _try_read_table("inventory_report", "inventory_report")
    reviews  = _try_read_table("reviews_social",   "reviews_social")
    mkt      = _try_read_table("market_data",      "market_data")
    forecast = _try_read_table("forecast_output",  "forecast_output")
    return inv, reviews, mkt, forecast


# ── 1 & 2 : SalesIndex, MarginIndex ──────────────────────────────────────────

def compute_sales_margin_indices(delist_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute SalesIndex and MarginIndex directly from the existing delist_df
    columns (no additional source files required).

    SalesIndex  = SKU total_revenue / mean(total_revenue) within the same
                  (granularity_level, granularity_value, Sub_Category) group.
                  >1 = above-average revenue performer; <1 = below average.

    MarginIndex = SKU margin_pct / mean(margin_pct) within the same group,
                  where margin_pct = total_margin / total_revenue.
                  >1 = better margin than peers; <1 = worse margin than peers.

    Both are NaN when the group has zero total revenue.
    """
    df = delist_df.copy()

    # SKU-level margin % (guarded divide)
    df["_margin_pct"] = _safe_div(df["total_margin"], df["total_revenue"], fill=np.nan)

    group_cols = ["granularity_level", "granularity_value", "Sub_Category"]
    grp = (
        df.groupby(group_cols, as_index=False)
          .agg(_avg_rev=("total_revenue", "mean"),
               _avg_marg=("_margin_pct",  "mean"))
    )
    df = df.merge(grp, on=group_cols, how="left")

    df["SalesIndex"]  = _safe_div(df["total_revenue"], df["_avg_rev"]).round(4)
    df["MarginIndex"] = _safe_div(df["_margin_pct"],   df["_avg_marg"]).round(4)

    return df.drop(columns=["_margin_pct", "_avg_rev", "_avg_marg"])


# ── 3, 4, 8 : VelocityIndex, InventoryEfficiency, GMROI ──────────────────────

def compute_granular_inventory_metrics(
    tx: pd.DataFrame,
    inv: pd.DataFrame,
    store_master: pd.DataFrame,
    sku_master: pd.DataFrame = None,
) -> pd.DataFrame:
    """
    Compute three inventory-based metrics at all four granularity levels.

    VelocityIndex (inventory turns)
        = Units_Sold / avg(Inventory_On_Hand)
        High value = fast-moving SKU relative to its stock level.

    InventoryEfficiency
        = 7 / avg(Days_Of_Supply)   [converts days → weekly efficiency]
        High value = lean inventory (turns over quickly); low = overstocked.
        Equals 1/WeeksOfSupply, as specified.

    GMROI (Gross Margin Return on Inventory Investment)
        = total_Gross_Margin_USD / avg(Inventory_Value)
        Standard retail profitability measure per dollar of inventory held.

    Granularity matching:
      Global    : all stores, all transactions
      Store     : single Store_ID (both tx and inventory filtered)
      Geography : stores in that geography (store→geo from Store_Master)
      Channel   : tx filtered by Channel; inventory has no channel dimension
                  so global inventory aggregation is used as the best available
                  proxy (documented assumption).

    Returns DataFrame with columns:
        granularity_level, granularity_value, SKU_ID,
        VelocityIndex, InventoryEfficiency, GMROI
    """
    if inv.empty:
        log.warning("  Inventory_Report.csv empty - VelocityIndex/InventoryEfficiency/GMROI will be NaN.")
        return pd.DataFrame(columns=[
            "granularity_level", "granularity_value", "SKU_ID",
            "VelocityIndex", "InventoryEfficiency", "GMROI",
        ])

    # Coerce numeric columns
    for col in ["Inventory_On_Hand", "Days_Of_Supply", "Inventory_Value"]:
        inv[col] = pd.to_numeric(inv[col], errors="coerce").fillna(0)
    for col in ["Units_Sold", "Gross_Margin_USD"]:
        tx[col] = pd.to_numeric(tx[col], errors="coerce").fillna(0)

    # Build SKU → unit cost lookup from SKU_Master for GMROI cost base.
    # Inventory_Value in this dataset equals Inventory_On_Hand (synthetic data
    # artefact where unit monetary value was not modelled separately).
    # Using Unit_Cost_USD × avg_inventory_units gives a defensible cost base.
    sku_unit_cost: Dict[str, float] = {}
    if sku_master is not None and not sku_master.empty:
        if "SKU_ID" in sku_master.columns and "Unit_Cost_USD" in sku_master.columns:
            sku_unit_cost = (
                pd.to_numeric(sku_master["Unit_Cost_USD"], errors="coerce")
                .fillna(0)
                .set_axis(sku_master["SKU_ID"])
                .to_dict()
            )

    # Pre-compute store → geography lookup
    store_geo: Dict[str, str] = {}
    if "Store_ID" in store_master.columns and "Geography" in store_master.columns:
        store_geo = store_master.set_index("Store_ID")["Geography"].to_dict()

    def _slice_metrics(
        tx_s: pd.DataFrame, inv_s: pd.DataFrame, level: str, value: str
    ) -> pd.DataFrame:
        """Compute the three metrics for one (level, value) slice."""
        if tx_s.empty and inv_s.empty:
            return pd.DataFrame()

        units = tx_s.groupby("SKU_ID")["Units_Sold"].sum()
        gm    = tx_s.groupby("SKU_ID")["Gross_Margin_USD"].sum()

        inv_agg = (
            inv_s.groupby("SKU_ID")
                 .agg(avg_inv_units  =("Inventory_On_Hand", "mean"),
                      avg_days_supply=("Days_Of_Supply",    "mean"))
        )

        # Outer-join so all SKUs from either source appear
        merged = (
            units.rename("units_sold").to_frame()
                 .join(gm.rename("total_gm"), how="outer")
                 .join(inv_agg,               how="outer")
                 .fillna({"units_sold": 0, "total_gm": 0})
        )

        merged["VelocityIndex"] = (
            _safe_div(merged["units_sold"], merged["avg_inv_units"]).round(4)
        )
        merged["InventoryEfficiency"] = np.where(
            merged["avg_days_supply"] > 0,
            (7.0 / merged["avg_days_supply"]).round(4),
            np.nan,
        )

        # GMROI = total gross margin / average inventory at cost.
        # avg_inv_cost = avg_inventory_units × SKU unit cost from SKU_Master.
        # This avoids the Inventory_Value field which equals Inventory_On_Hand
        # (units) in the synthetic dataset and would inflate GMROI.
        unit_costs = pd.Series(sku_unit_cost, name="unit_cost").reindex(merged.index).fillna(0)
        avg_inv_cost = merged["avg_inv_units"].fillna(0) * unit_costs
        merged["GMROI"] = _safe_div(merged["total_gm"], avg_inv_cost).round(4)

        out = (
            merged[["VelocityIndex", "InventoryEfficiency", "GMROI"]]
            .reset_index()  # index is SKU_ID
            .dropna(subset=["SKU_ID"])
        )
        out["granularity_level"] = level
        out["granularity_value"] = value
        return out

    parts: List[pd.DataFrame] = []

    # Global
    parts.append(_slice_metrics(tx, inv, "Global", "Global"))

    # Store level
    for store_id, tx_s in tx.groupby("Store_ID"):
        inv_s = inv[inv["Store_ID"] == store_id] if "Store_ID" in inv.columns else inv
        parts.append(_slice_metrics(tx_s, inv_s, "Store", str(store_id)))

    # Geography level
    inv["_geo"] = inv["Store_ID"].map(store_geo) if "Store_ID" in inv.columns else None
    for geo, tx_g in tx.groupby("Geography"):
        inv_g = inv[inv["_geo"] == geo]
        if inv_g.empty:
            inv_g = inv  # fallback: use full inventory if geo unmapped
        parts.append(_slice_metrics(tx_g, inv_g, "Geography", str(geo)))
    inv.drop(columns=["_geo"], inplace=True, errors="ignore")

    # Channel level — no channel in inventory; use global inventory as proxy
    for ch, tx_c in tx.groupby("Channel"):
        parts.append(_slice_metrics(tx_c, inv, "Channel", str(ch)))

    result = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    log.info(f"  Inventory metrics computed: {len(result):,} granularity×SKU rows.")
    return result


# ── 5 : SentimentIndex ───────────────────────────────────────────────────────

def compute_sentiment_index(reviews_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate Sentiment_Score at SKU level and normalize to [0, 1].

    Normalization method: min-max scaling across all SKU-level averages.
      1.0 = most positive sentiment relative to category peers
      0.0 = most negative sentiment relative to category peers

    If all SKU-level averages are identical, SentimentIndex = 0.5 (neutral).

    Returns DataFrame with columns: SKU_ID, SentimentIndex
    """
    if reviews_df.empty or "Sentiment_Score" not in reviews_df.columns:
        log.warning("  Reviews_Social.csv missing or lacks Sentiment_Score column.")
        return pd.DataFrame(columns=["SKU_ID", "SentimentIndex"])

    reviews = reviews_df.copy()
    reviews["Sentiment_Score"] = pd.to_numeric(reviews["Sentiment_Score"], errors="coerce")

    sku_sent = (
        reviews.groupby("SKU_ID")["Sentiment_Score"]
               .mean()
               .reset_index(name="avg_sentiment")
    )

    sku_sent["SentimentIndex"] = _min_max_norm(
        sku_sent["avg_sentiment"]
    ).round(4)

    log.info(f"  SentimentIndex computed for {len(sku_sent)} SKUs.")
    return sku_sent[["SKU_ID", "SentimentIndex"]]


# ── 6 : MarketStrengthIndex ───────────────────────────────────────────────────

def compute_market_strength_index(market_data_df: pd.DataFrame) -> pd.DataFrame:
    """
    MarketStrengthIndex = 0.35 * MarketShare
                        + 0.30 * ShareGrowth
                        + 0.20 * SubCategoryGrowth
                        + 0.15 * DistributionTrend

    Each of the four components is min-max normalized to [0, 1] before
    weighting so that no single metric dominates due to scale differences.

    Assumptions / methodology:
      MarketShare      : 'Market Share %' — higher = stronger relative position
      ShareGrowth      : 'Share Change vs YA' — positive = gaining; normalized
                         so the most negative change maps to 0, highest to 1
      SubCategoryGrowth: 'Category Growth %' — broad category tailwind/headwind
                         (same for all SKUs in a sub-category but varies across
                          sub-categories, providing inter-category signal)
      DistributionTrend: 'Distribution Trend' encoded as
                         Growing → 1.0, Stable → 0.5, Declining → 0.0
                         then min-max normalized across the encoded values

    Returns DataFrame with columns: SKU_ID, MarketStrengthIndex
    """
    required_cols = [
        "SKU_ID", "Market Share %", "Share Change vs YA",
        "Category Growth %", "Distribution Trend",
    ]
    if market_data_df.empty:
        log.warning("  Market_Data.csv empty - MarketStrengthIndex will be NaN.")
        return pd.DataFrame(columns=["SKU_ID", "MarketStrengthIndex"])
    missing = [c for c in required_cols if c not in market_data_df.columns]
    if missing:
        log.warning(f"  Market_Data.csv missing columns {missing} - MarketStrengthIndex will be NaN.")
        return pd.DataFrame(columns=["SKU_ID", "MarketStrengthIndex"])

    df = market_data_df[required_cols].copy()

    for col in ["Market Share %", "Share Change vs YA", "Category Growth %"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    dist_map = {"Growing": 1.0, "Stable": 0.5, "Declining": 0.0}
    df["_dist"] = df["Distribution Trend"].map(dist_map).fillna(0.5)

    n_mkt   = _min_max_norm(df["Market Share %"])
    n_share = _min_max_norm(df["Share Change vs YA"])
    n_subcat= _min_max_norm(df["Category Growth %"])
    n_dist  = _min_max_norm(df["_dist"])

    df["MarketStrengthIndex"] = (
        0.35 * n_mkt + 0.30 * n_share + 0.20 * n_subcat + 0.15 * n_dist
    ).round(4)

    log.info(f"  MarketStrengthIndex computed for {len(df)} SKUs.")
    return df[["SKU_ID", "MarketStrengthIndex"]]


# ── 9 : Forecast / Trend Metrics ─────────────────────────────────────────────

def compute_granular_forecast_metrics(
    forecast_df: pd.DataFrame,
    store_master: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute four forecast-based metrics at all granularity levels.

    Forecasted_Sales    : Sum of Final_Forecast over the full 6-week horizon
                          for the given (level, value, SKU) combination.

    Forecast_Growth_Pct : Intra-horizon trend.
                          = (avg second-half weeks − avg first-half weeks)
                            / avg first-half weeks × 100
                          Positive = momentum building within the forecast
                          window; negative = decelerating.

    Trend_Direction     : Categorical encoding of Forecast_Growth_Pct:
                          'Upward' (> +2%), 'Stable' (−2% to +2%),
                          'Downward' (< −2%).

    Forecast_Confidence : Measure of forecast interval tightness.
                          = 1 − mean(range_width / final_forecast per week)
                          where range_width = Highest − Lowest forecast range.
                          1.0 = perfectly certain; 0.0 = extremely wide range.

    For Channel granularity, Forecast_Output.csv carries no channel dimension.
    The corresponding Global-level SKU values are used as the best available
    proxy (clearly documented as an assumption).

    Returns DataFrame with:
        granularity_level, granularity_value, SKU_ID,
        Forecasted_Sales, Forecast_Growth_Pct, Trend_Direction, Forecast_Confidence
    """
    EMPTY_COLS = [
        "granularity_level", "granularity_value", "SKU_ID",
        "Forecasted_Sales", "Forecast_Growth_Pct",
        "Trend_Direction", "Forecast_Confidence",
    ]
    if forecast_df.empty:
        log.warning("  Forecast_Output.csv empty - forecast metrics will be NaN.")
        return pd.DataFrame(columns=EMPTY_COLS)

    fc = forecast_df.copy()
    for col in ["Final_Forecast", "Forecast_Lower", "Forecast_Upper"]:
        if col in fc.columns:
            fc[col] = pd.to_numeric(fc[col], errors="coerce").fillna(0.0)
    lo = fc["Forecast_Lower"] if "Forecast_Lower" in fc.columns else fc["Final_Forecast"] * 0.95
    hi = fc["Forecast_Upper"] if "Forecast_Upper" in fc.columns else fc["Final_Forecast"] * 1.05
    fc["_range_width"] = (hi - lo).clip(lower=0)
    fc = fc.sort_values("Forecast_Week").reset_index(drop=True)

    def _agg(slice_df: pd.DataFrame, level: str, value: str) -> pd.DataFrame:
        if slice_df.empty:
            return pd.DataFrame(columns=EMPTY_COLS)
        rows: List[dict] = []
        for sku_id, sku_fc in slice_df.groupby("SKU_ID"):
            sku_fc = sku_fc.sort_values("Forecast_Week")
            forecasts = sku_fc["Final_Forecast"].values
            n = len(forecasts)
            total_sales = float(forecasts.sum())

            mid = max(1, n // 2)
            first_avg  = float(forecasts[:mid].mean()) if mid > 0 else 0.0
            second_avg = float(forecasts[mid:].mean()) if n > mid else first_avg

            growth_pct = (
                (second_avg - first_avg) / first_avg * 100
                if first_avg > 0 else 0.0
            )
            trend_dir = (
                "Upward" if growth_pct > 2.0
                else "Downward" if growth_pct < -2.0
                else "Stable"
            )

            # Relative range width per week; clip to [0, 1]
            rel_range = np.where(
                sku_fc["Final_Forecast"].values > 0,
                sku_fc["_range_width"].values / sku_fc["Final_Forecast"].values,
                0.0,
            )
            confidence = float(np.clip(1.0 - rel_range.mean(), 0.0, 1.0))

            rows.append({
                "granularity_level":   level,
                "granularity_value":   value,
                "SKU_ID":              sku_id,
                "Forecasted_Sales":    round(total_sales, 2),
                "Forecast_Growth_Pct": round(growth_pct,  2),
                "Trend_Direction":     trend_dir,
                "Forecast_Confidence": round(confidence,  4),
            })
        return pd.DataFrame(rows)

    store_geo: Dict[str, str] = {}
    if "Store_ID" in store_master.columns and "Geography" in store_master.columns:
        store_geo = store_master.set_index("Store_ID")["Geography"].to_dict()

    parts: List[pd.DataFrame] = [_agg(fc, "Global", "Global")]

    if "Store_ID" in fc.columns:
        for store_id, grp in fc.groupby("Store_ID"):
            parts.append(_agg(grp, "Store", str(store_id)))

    if "Geography" in fc.columns:
        for geo, grp in fc.groupby("Geography"):
            parts.append(_agg(grp, "Geography", str(geo)))

    result = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    log.info(f"  Forecast metrics computed: {len(result):,} granularity×SKU rows.")
    return result


# ── 7 : Health_Score ─────────────────────────────────────────────────────────

def compute_health_score(delist_df: pd.DataFrame) -> pd.DataFrame:
    """
    Health_Score = 0.25 * SalesIndex
                 + 0.15 * MarginIndex
                 + 0.15 * VelocityIndex
                 + 0.15 * SentimentIndex
                 + 0.10 * InventoryEfficiency
                 + 0.20 * MarketStrengthIndex

    Each component is independently min-max normalized to [0, 1] across ALL
    rows in delist_df before weighting, so that differences in raw scale
    (e.g., GMROI in the hundreds vs SentimentIndex in 0–1) do not distort
    the composite score.

    Missing component values are imputed with the component's median before
    normalization so that every row receives a Health_Score.  The imputed
    proportion is logged for transparency.

    Interpretation: 1.0 = strongest performer across all six dimensions,
                    0.0 = weakest. Not a probability — use as a relative rank.
    """
    df = delist_df.copy()

    components: Dict[str, float] = {
        "SalesIndex":          0.25,
        "MarginIndex":         0.15,
        "VelocityIndex":       0.15,
        "SentimentIndex":      0.15,
        "InventoryEfficiency": 0.10,
        "MarketStrengthIndex": 0.20,
    }

    for col in components:
        if col not in df.columns:
            df[col] = np.nan

    weighted = pd.Series(0.0, index=df.index)
    for col, weight in components.items():
        series = pd.to_numeric(df[col], errors="coerce")
        null_n = series.isna().sum()
        if null_n > 0:
            med = series.median()
            series = series.fillna(med if pd.notna(med) else 0.0)
            log.info(f"    Health_Score: {null_n} nulls in {col} imputed with median={med:.3f}")
        weighted += weight * _min_max_norm(series)

    df["Health_Score"] = weighted.round(4)
    return df


# ── Orchestrator ──────────────────────────────────────────────────────────────

def enrich_with_kpis(
    delist_df: pd.DataFrame,
    tx: pd.DataFrame,
    inv: pd.DataFrame,
    store_master: pd.DataFrame,
    reviews: pd.DataFrame,
    market_data: pd.DataFrame,
    forecast_df: pd.DataFrame,
    sku_master: pd.DataFrame = None,
) -> pd.DataFrame:
    """
    Orchestrate enrichment of delist_df with all 12 new KPI columns.
    Existing columns (including delist_score) are preserved unchanged.

    Join strategy:
      SalesIndex, MarginIndex   : derived from delist_df — no join needed
      VelocityIndex, Inventory
        Efficiency, GMROI       : joined on (granularity_level, granularity_value, SKU_ID)
      SentimentIndex            : joined on SKU_ID (SKU-level; same across granularities)
      MarketStrengthIndex       : joined on SKU_ID (SKU-level)
      Forecast metrics          : joined on (granularity_level, granularity_value, SKU_ID);
                                  Channel rows fall back to Global SKU values
      Health_Score              : computed last, after all components are present
    """
    log.info("-" * 50)
    log.info("STEP: Enriching delist recommendations with enhanced KPIs")
    n_before = len(delist_df)
    join_keys = ["granularity_level", "granularity_value", "SKU_ID"]

    # 1 & 2: SalesIndex, MarginIndex (from delist_df itself)
    delist_df = compute_sales_margin_indices(delist_df)
    log.info("  [OK] SalesIndex, MarginIndex")

    # 3, 4, 8: VelocityIndex, InventoryEfficiency, GMROI
    inv_metrics = compute_granular_inventory_metrics(tx, inv, store_master, sku_master)
    if not inv_metrics.empty:
        inv_cols = join_keys + ["VelocityIndex", "InventoryEfficiency", "GMROI"]
        delist_df = delist_df.merge(inv_metrics[inv_cols], on=join_keys, how="left")
    else:
        for col in ["VelocityIndex", "InventoryEfficiency", "GMROI"]:
            delist_df[col] = np.nan
    log.info(
        f"  [OK] VelocityIndex/InventoryEfficiency/GMROI  "
        f"({delist_df['VelocityIndex'].notna().sum()}/{n_before} rows covered)"
    )

    # 5: SentimentIndex (SKU-level join)
    sentiment = compute_sentiment_index(reviews)
    if not sentiment.empty:
        delist_df = delist_df.merge(sentiment, on="SKU_ID", how="left")
    else:
        delist_df["SentimentIndex"] = np.nan
    log.info(
        f"  [OK] SentimentIndex  "
        f"({delist_df['SentimentIndex'].notna().sum()}/{n_before} rows covered)"
    )

    # 6: MarketStrengthIndex (SKU-level join)
    msi = compute_market_strength_index(market_data)
    if not msi.empty:
        delist_df = delist_df.merge(msi, on="SKU_ID", how="left")
    else:
        delist_df["MarketStrengthIndex"] = np.nan
    log.info(
        f"  [OK] MarketStrengthIndex  "
        f"({delist_df['MarketStrengthIndex'].notna().sum()}/{n_before} rows covered)"
    )

    # 9: Forecast metrics (granularity-aware join + Channel fallback)
    fc_metrics = compute_granular_forecast_metrics(forecast_df, store_master)
    if not fc_metrics.empty:
        fc_cols = join_keys + [
            "Forecasted_Sales", "Forecast_Growth_Pct",
            "Trend_Direction", "Forecast_Confidence",
        ]
        delist_df = delist_df.merge(fc_metrics[fc_cols], on=join_keys, how="left")

        # Channel rows have no match in Forecast_Output → fall back to Global values
        global_fc = (
            fc_metrics[fc_metrics["granularity_level"] == "Global"]
            [["SKU_ID", "Forecasted_Sales", "Forecast_Growth_Pct",
              "Trend_Direction", "Forecast_Confidence"]]
            .rename(columns={c: f"_fb_{c}" for c in
                             ["Forecasted_Sales", "Forecast_Growth_Pct",
                              "Trend_Direction", "Forecast_Confidence"]})
        )
        delist_df = delist_df.merge(global_fc, on="SKU_ID", how="left")
        for orig in ["Forecasted_Sales", "Forecast_Growth_Pct",
                     "Trend_Direction", "Forecast_Confidence"]:
            fb_col = f"_fb_{orig}"
            delist_df[orig] = delist_df[orig].fillna(delist_df[fb_col])
        delist_df.drop(
            columns=[c for c in delist_df.columns if c.startswith("_fb_")],
            inplace=True,
        )
    else:
        for col in ["Forecasted_Sales", "Forecast_Growth_Pct",
                    "Trend_Direction", "Forecast_Confidence"]:
            delist_df[col] = np.nan
    log.info(
        f"  [OK] Forecast metrics  "
        f"({delist_df['Forecasted_Sales'].notna().sum()}/{n_before} rows covered)"
    )

    # 7: Health_Score (must be last — needs all components present)
    delist_df = compute_health_score(delist_df)
    log.info("  [OK] Health_Score")

    # ── Validation ────────────────────────────────────────────────────────────
    n_after = len(delist_df)
    if n_after != n_before:
        log.warning(
            f"  Row count changed after enrichment: {n_before:,} -> {n_after:,}. "
            "Deduplicating on (granularity_level, granularity_value, SKU_ID)."
        )
        delist_df = (
            delist_df
            .drop_duplicates(subset=join_keys, keep="first")
            .reset_index(drop=True)
        )
    else:
        log.info(f"  Row count validated: {n_before:,} rows maintained.")

    dup_check = delist_df.duplicated(subset=join_keys).sum()
    if dup_check:
        log.warning(f"  {dup_check} duplicate rows remain after dedup — investigate join keys.")

    return delist_df


def print_kpi_summary(delist_df: pd.DataFrame) -> None:
    """
    Log summary statistics and range validation for all new KPI columns.
    Reported at Global granularity level only for conciseness.
    """
    global_df = delist_df[delist_df["granularity_level"] == "Global"].copy()
    n = len(global_df)

    kpi_cols = [
        "Health_Score", "GMROI", "MarketStrengthIndex", "SentimentIndex",
        "SalesIndex", "MarginIndex", "VelocityIndex", "InventoryEfficiency",
        "Forecasted_Sales", "Forecast_Growth_Pct", "Forecast_Confidence",
    ]

    log.info("")
    log.info("=" * 60)
    log.info(f"ENHANCED KPI SUMMARY  (Global level, {n} SKUs)")
    log.info("=" * 60)
    for col in kpi_cols:
        if col not in global_df.columns or global_df[col].isna().all():
            log.info(f"  {col:<28s} NOT AVAILABLE")
            continue
        vals = pd.to_numeric(global_df[col], errors="coerce").dropna()
        log.info(
            f"  {col:<28s} mean={vals.mean():>8.3f}  "
            f"min={vals.min():>8.3f}  max={vals.max():>8.3f}  "
            f"cov={len(vals)}/{n}"
        )

    log.info("")
    log.info("  Range validation (0–1 bounded indices):")
    for col in ["Health_Score", "MarketStrengthIndex", "SentimentIndex", "Forecast_Confidence"]:
        if col in global_df.columns:
            vals = pd.to_numeric(global_df[col], errors="coerce").dropna()
            out  = int(((vals < 0) | (vals > 1)).sum())
            log.info(f"    {col:<28s} values outside [0,1]: {out}")

    log.info("=" * 60)


# =============================================================================
# SECTION 10: ADVANCED DECISION ENGINE
# =============================================================================
# Classifies each recommendation row into metric bands, applies a priority-
# ordered decision framework (9 states), and generates business-ready narrative
# output for category managers.  Replaces the legacy 'recommendation' and
# 'nl_summary' columns with four richer output columns:
#   Health_Band, Delist_Band, GMROI_Band, Forecast_Band,
#   Decision, Decision_Reason, Recommended_Action, Recommendation_Narrative
# =============================================================================

# ── Band threshold constants ──────────────────────────────────────────────────
HEALTH_HIGH_THRESHOLD  = 0.70   # Health_Score >= this → HIGH_HEALTH
HEALTH_MID_THRESHOLD   = 0.45   # Health_Score >= this → MID_HEALTH (else LOW)
DELIST_HIGH_THRESHOLD  = 0.70   # delist_score >= this → HIGH_DELIST
DELIST_MID_THRESHOLD   = 0.40   # delist_score >= this → MID_DELIST (else LOW)
FORECAST_STRONG_GROWTH = 15.0   # Forecast_Growth_Pct >= this → STRONG_GROWTH
FORECAST_GROWTH_MIN    =  5.0   # >= this (< STRONG_GROWTH) → GROWTH
FORECAST_DECLINE_MAX   = -5.0   # <= this → DECLINE
FORECAST_SHARP_DECLINE = -15.0  # <= this → SHARP_DECLINE
# GMROI bands are percentile-based (see classify_metric_bands)
GMROI_HIGH_PCTILE      = 66     # above this percentile → HIGH_GMROI
GMROI_LOW_PCTILE       = 33     # below this percentile → LOW_GMROI
BASKET_ANCHOR_MIN_DEP  =  4     # dependency score >= this → Anchor role
BASKET_COMPLEMENT_MIN  =  2     # dependency score >= this → Complement role


# ── Band classification ───────────────────────────────────────────────────────

def classify_metric_bands(df: pd.DataFrame) -> pd.DataFrame:
    """
    Append four band columns and three derived helper columns to df.

    Band columns
    ------------
    Health_Band   : HIGH_HEALTH / MID_HEALTH / LOW_HEALTH
                    Fixed thresholds (0.45, 0.70).
    Delist_Band   : HIGH_DELIST / MID_DELIST / LOW_DELIST
                    Fixed thresholds (0.40, 0.70).
    GMROI_Band    : HIGH_GMROI / MID_GMROI / LOW_GMROI
                    Percentile-based (33rd / 66th) over valid GMROI values so
                    that classification is relative to the current dataset rather
                    than an arbitrary absolute scale.
    Forecast_Band : STRONG_GROWTH / GROWTH / FLAT / DECLINE / SHARP_DECLINE
                    Fixed thresholds on Forecast_Growth_Pct.

    Helper columns (consumed by decision logic and narratives)
    ----------------------------------------------------------
    Basket_Role         : Anchor / Complement / Substitutable / Solo
    Recapture_Potential : substitution_score (0–1); high = many alternatives
    Cannibalization_Risk: normalized basket_dependency_score (0–1); high = more
                          disruption if delisted.

    NaN inputs default to the middle band to avoid spurious extreme decisions.
    """
    df = df.copy()

    # ── Health Band (adaptive percentile-based) ───────────────────────────────
    # Fixed thresholds (0.70 / 0.45) assume a uniform [0,1] distribution.
    # In practice Health_Score clusters low due to VelocityIndex scale effects,
    # so we use 66th / 33rd percentile thresholds for a meaningful split.
    hs = pd.to_numeric(df["Health_Score"], errors="coerce")
    valid_hs = hs.dropna()
    if len(valid_hs) >= 3:
        hs_p_hi = float(np.percentile(valid_hs, GMROI_HIGH_PCTILE))
        hs_p_lo = float(np.percentile(valid_hs, GMROI_LOW_PCTILE))
    else:
        hs_p_hi, hs_p_lo = HEALTH_HIGH_THRESHOLD, HEALTH_MID_THRESHOLD
    df["Health_Band"] = np.where(
        hs >= hs_p_hi, "HIGH_HEALTH",
        np.where(hs >= hs_p_lo, "MID_HEALTH", "LOW_HEALTH"),
    )
    df.loc[hs.isna(), "Health_Band"] = "MID_HEALTH"
    log.info(
        f"  Health band thresholds (adaptive): "
        f"LOW < {hs_p_lo:.4f} <= MID < {hs_p_hi:.4f} <= HIGH"
    )

    # ── Delist Band ────────────────────────────────────────────────────────────
    ds = pd.to_numeric(df["delist_score"], errors="coerce")
    df["Delist_Band"] = np.where(
        ds >= DELIST_HIGH_THRESHOLD, "HIGH_DELIST",
        np.where(ds >= DELIST_MID_THRESHOLD, "MID_DELIST", "LOW_DELIST"),
    )
    df.loc[ds.isna(), "Delist_Band"] = "MID_DELIST"

    # ── GMROI Band (percentile-based) ─────────────────────────────────────────
    gmroi = pd.to_numeric(df.get("GMROI", pd.Series(np.nan, index=df.index)),
                          errors="coerce")
    valid_g = gmroi.dropna()
    if len(valid_g) >= 3:
        p_lo = float(np.percentile(valid_g, GMROI_LOW_PCTILE))
        p_hi = float(np.percentile(valid_g, GMROI_HIGH_PCTILE))
    else:
        p_lo, p_hi = 0.0, float(valid_g.max()) if len(valid_g) > 0 else 1.0
    df["GMROI_Band"] = np.where(
        gmroi >= p_hi, "HIGH_GMROI",
        np.where(gmroi >= p_lo, "MID_GMROI", "LOW_GMROI"),
    )
    df.loc[gmroi.isna(), "GMROI_Band"] = "MID_GMROI"
    log.info(
        f"  GMROI band thresholds (percentile-based): "
        f"LOW < {p_lo:,.1f} <= MID < {p_hi:,.1f} <= HIGH"
    )

    # ── Forecast Band ──────────────────────────────────────────────────────────
    fgp = pd.to_numeric(
        df.get("Forecast_Growth_Pct", pd.Series(np.nan, index=df.index)),
        errors="coerce",
    )

    def _fb(v: float) -> str:
        if pd.isna(v):              return "FLAT"
        if v >= FORECAST_STRONG_GROWTH: return "STRONG_GROWTH"
        if v >= FORECAST_GROWTH_MIN:    return "GROWTH"
        if v > FORECAST_DECLINE_MAX:    return "FLAT"
        if v > FORECAST_SHARP_DECLINE:  return "DECLINE"
        return "SHARP_DECLINE"

    df["Forecast_Band"] = fgp.apply(_fb)

    # ── Basket Role (adaptive percentile-based thresholds) ────────────────────
    # Fixed thresholds (dep >= 4 → Anchor) over-classify when the dependency
    # score distribution is wide (e.g. 80 %+ Anchors).  Use the 75th percentile
    # of non-zero dep scores for the Anchor cut-off and 40th for Complement.
    dep = pd.to_numeric(df.get("basket_dependency_score", 0), errors="coerce").fillna(0)
    sub = pd.to_numeric(df.get("substitution_score",       0), errors="coerce").fillna(0)
    dep_nonzero = dep[dep > 0]
    if len(dep_nonzero) >= 4:
        anchor_thresh = float(np.percentile(dep_nonzero, 75))
        comp_thresh   = float(np.percentile(dep_nonzero, 40))
    else:
        anchor_thresh, comp_thresh = float(BASKET_ANCHOR_MIN_DEP), float(BASKET_COMPLEMENT_MIN)
    df["Basket_Role"] = np.where(
        dep >= anchor_thresh, "Anchor",
        np.where(dep >= comp_thresh, "Complement",
        np.where(sub >= 0.5,        "Substitutable", "Solo")),
    )
    log.info(
        f"  Basket role thresholds (adaptive): "
        f"Anchor >= {anchor_thresh:.1f}, Complement >= {comp_thresh:.1f}"
    )

    # ── Recapture Potential ────────────────────────────────────────────────────
    # Derived from substitution_score: higher = more in-category alternatives exist
    df["Recapture_Potential"] = sub.round(4)

    # ── Cannibalization Risk ───────────────────────────────────────────────────
    # Derived from basket_dependency_score: higher = more disruption if delisted
    max_dep = float(dep.max()) if dep.max() > 0 else 1.0
    df["Cannibalization_Risk"] = (dep / max_dep).round(4)

    return df


# ── Decision logic ────────────────────────────────────────────────────────────

def _apply_single_decision(row: pd.Series) -> str:
    """
    Apply the nine decision rules in strict priority order.
    Returns the first matching Decision label.

    Priority (highest → lowest):
        1 EXPAND  2 FUTURE_STAR  3 KEEP  4 CASH_COW
        5 INVESTIGATE  6 KEEP_WATCH  7 PHASE_OUT  8 REPLACE  9 DELIST
    """
    h = str(row.get("Health_Band",  "MID_HEALTH"))
    d = str(row.get("Delist_Band",  "MID_DELIST"))
    g = str(row.get("GMROI_Band",   "MID_GMROI"))
    f = str(row.get("Forecast_Band","FLAT"))
    role     = str(row.get("Basket_Role",         "Solo"))
    recapture= float(row.get("Recapture_Potential",  0) or 0)
    cannib   = float(row.get("Cannibalization_Risk", 0) or 0)

    # ── Boolean aliases ────────────────────────────────────────────────────────
    h_hi = h == "HIGH_HEALTH";  h_mi = h == "MID_HEALTH";  h_lo = h == "LOW_HEALTH"
    d_hi = d == "HIGH_DELIST";  d_mi = d == "MID_DELIST";  d_lo = d == "LOW_DELIST"
    g_hi = g == "HIGH_GMROI";   g_mi = g == "MID_GMROI";   g_lo = g == "LOW_GMROI"

    f_sg  = f == "STRONG_GROWTH"
    f_gr  = f in ("GROWTH", "STRONG_GROWTH")     # active growth
    f_fl  = f == "FLAT"
    f_dc  = f in ("DECLINE", "SHARP_DECLINE")    # any decline
    f_sd  = f == "SHARP_DECLINE"
    f_nd  = not f_dc                              # not declining

    is_anchor      = role == "Anchor"
    recapture_hi   = recapture >= 0.5
    cannib_lo      = cannib < 0.4

    # Conflicting-signal detection (triggers INVESTIGATE)
    # Deliberately narrow: INVESTIGATE should surface only genuine contradictions,
    # not every below-average SKU with a basket role (those go to KEEP_WATCH).
    fg_val = float(row.get("Forecast_Growth_Pct", 0) or 0)
    has_conflict = (
        (h_hi and g_lo)                              # strong overall health, poor space ROI
        or (fg_val >= FORECAST_GROWTH_MIN and d_hi)  # market growing but delist signal high
    )

    # ── 1. EXPAND ─────────────────────────────────────────────────────────────
    if h_hi and f_gr and (g_hi or g_mi) and d_lo:
        return "EXPAND"

    # ── 2. FUTURE_STAR ────────────────────────────────────────────────────────
    # Emerging SKU: moderate health offset by strong forecast momentum
    if h_mi and f_sg and (d_lo or d_mi):
        return "FUTURE_STAR"

    # ── 3. KEEP ───────────────────────────────────────────────────────────────
    # Profitable, stable-to-positive; EXPAND already claimed h_hi+f_gr cases
    if h_hi and g_hi and d_lo and f_nd:
        return "KEEP"

    # ── 4. CASH_COW ───────────────────────────────────────────────────────────
    # Profitable but explicitly declining; harvest strategy
    if h_hi and (g_hi or g_mi) and f_dc and d_lo:
        return "CASH_COW"

    # ── 5. INVESTIGATE ────────────────────────────────────────────────────────
    if has_conflict:
        return "INVESTIGATE"

    # ── 6. KEEP_WATCH ─────────────────────────────────────────────────────────
    # Anchor basket role justifies near-term retention despite below-average health
    if (h_mi or h_lo) and (d_lo or d_mi) and is_anchor:
        return "KEEP_WATCH"
    # Moderate health + moderate delist risk + no decline → monitor, not act
    if h_mi and d_mi and f_nd:
        return "KEEP_WATCH"

    # ── 7. PHASE_OUT ──────────────────────────────────────────────────────────
    # Any decline + below-average health + delist pressure → gradual exit
    if (h_mi or h_lo) and f_dc and (d_mi or d_hi):
        return "PHASE_OUT"

    # ── 8. REPLACE ────────────────────────────────────────────────────────────
    # Weak but substitutable; preserve category role via transition
    if h_lo and d_hi and recapture_hi and cannib_lo:
        return "REPLACE"

    # ── 9. DELIST ─────────────────────────────────────────────────────────────
    # All exit criteria confirmed
    if h_lo and d_hi and g_lo and f_dc and recapture_hi and not is_anchor:
        return "DELIST"

    # ── Fallback: cover any remaining combinations ─────────────────────────────
    if h_lo and d_hi:
        return "DELIST"
    if (h_mi or h_lo) and (d_mi or d_hi):
        return "PHASE_OUT"
    if h_lo:
        return "KEEP_WATCH"
    return "KEEP"


# ── Narrative builders ────────────────────────────────────────────────────────

_FORECAST_BAND_TEXT: Dict[str, str] = {
    "STRONG_GROWTH": "strong forecast growth",
    "GROWTH":        "positive forecast growth",
    "FLAT":          "flat forecast",
    "DECLINE":       "declining forecast",
    "SHARP_DECLINE": "sharply declining forecast",
}


def _build_decision_reason(row: pd.Series) -> str:
    """
    Concise 1–2 sentence summary of the primary drivers behind the Decision.
    References band labels and rounded KPI values for audit traceability.
    """
    dec    = str(row.get("Decision",    "KEEP"))
    h_band = str(row.get("Health_Band", "MID_HEALTH"))
    d_band = str(row.get("Delist_Band", "MID_DELIST"))
    g_band = str(row.get("GMROI_Band",  "MID_GMROI"))
    f_band = str(row.get("Forecast_Band","FLAT"))
    role   = str(row.get("Basket_Role", "Solo"))
    hs     = row.get("Health_Score",        np.nan)
    ds     = row.get("delist_score",        np.nan)
    fg     = row.get("Forecast_Growth_Pct", np.nan)

    hs_s = f"{hs:.2f}" if pd.notna(hs) else "N/A"
    ds_s = f"{ds:.2f}" if pd.notna(ds) else "N/A"
    fg_s = f"{fg:+.1f}%" if pd.notna(fg) else "N/A"
    fb_t = _FORECAST_BAND_TEXT.get(f_band, f_band.lower())

    reasons: Dict[str, str] = {
        "EXPAND":      (
            f"{h_band} health ({hs_s}) with {g_band} inventory productivity "
            f"and {fb_t} ({fg_s}) confirm expansion viability. Delist risk is low."
        ),
        "FUTURE_STAR": (
            f"Moderate health ({hs_s}) offset by strong forecast momentum ({fg_s}). "
            f"Delist risk ({d_band}) is manageable, supporting retention over rationalization."
        ),
        "KEEP":        (
            f"Solid commercial health ({hs_s}), {g_band} GMROI, and {fb_t} ({fg_s}) "
            f"confirm core assortment status. Delist risk is low."
        ),
        "CASH_COW":    (
            f"Mature profitable SKU: {h_band} health ({hs_s}) and {g_band} GMROI "
            f"despite {fb_t} ({fg_s}). Low delist risk supports a harvest strategy."
        ),
        "INVESTIGATE": (
            f"Conflicting signals: {h_band} health vs {g_band} GMROI and {fb_t} ({fg_s}). "
            f"Basket role '{role}' adds ambiguity. Manual review required before action."
        ),
        "KEEP_WATCH":  (
            f"{h_band} health ({hs_s}) and {d_band} delist pressure with {fb_t} ({fg_s}). "
            f"Basket role '{role}' justifies short-term retention pending closer monitoring."
        ),
        "PHASE_OUT":   (
            f"Sharp forecast decline ({fg_s}), {h_band} health ({hs_s}), "
            f"and {d_band} delist signal ({ds_s}) indicate an unsustainable commercial trajectory."
        ),
        "REPLACE":     (
            f"{h_band} health ({hs_s}) and {d_band} delist risk ({ds_s}) with "
            f"high recapture potential confirm substitution opportunity with low disruption risk."
        ),
        "DELIST":      (
            f"{h_band} health ({hs_s}), {g_band} GMROI, {fb_t} ({fg_s}), "
            f"and {d_band} delist score ({ds_s}) all confirm removal viability."
        ),
    }
    return reasons.get(dec, f"Decision driven by {h_band}, {d_band}, {g_band}, {fb_t}.")


def _build_recommended_action(row: pd.Series) -> str:
    """Concise, operational action statement for planners and buyers."""
    dec  = str(row.get("Decision",    "KEEP"))
    role = str(row.get("Basket_Role", "Solo"))

    actions: Dict[str, str] = {
        "EXPAND":      (
            "Increase shelf facings and replenishment depth. Expand distribution to "
            "under-indexed stores. Protect instock levels and prioritize service rate."
        ),
        "FUTURE_STAR": (
            "Retain in full distribution. Selectively increase visibility (endcap, digital "
            "spotlight). Re-evaluate commercial KPIs at the next review cycle."
        ),
        "KEEP":        (
            "Maintain current planogram allocation and supply continuity. "
            "Protect from unnecessary rationalization pressure."
        ),
        "CASH_COW":    (
            "Optimize shelf pricing and reduce promotional investment. "
            "Protect gross margin; do not expand distribution further."
        ),
        "INVESTIGATE": (
            "Escalate to category review team. Conduct deep-dive on GMROI drivers "
            "and basket contribution before next planogram action."
        ),
        "KEEP_WATCH":  (
            "Maintain current distribution. Set performance trigger thresholds "
            "for the next review cycle. Avoid incremental investment."
        ),
        "PHASE_OUT":   (
            "Reduce shelf facings by ~50% at next planogram reset. "
            "Discontinue promotional support. Notify supply chain of planned exit."
        ),
        "REPLACE":     (
            "Identify strongest substitute from the demand transfer matrix. "
            "Stage shelf space transition. Align supply chain on delisting timeline."
        ),
        "DELIST":      (
            "Remove from planogram at next reset. Cancel open purchase orders. "
            "Reallocate shelf space and procurement budget to higher-performing SKUs."
        ),
    }
    base = actions.get(dec, "Review with category management team.")
    if role == "Anchor" and dec in ("DELIST", "REPLACE", "PHASE_OUT"):
        base += (
            " CAUTION: This SKU has an Anchor basket role — "
            "confirm recapture plan before executing exit."
        )
    return base


def _build_recommendation_narrative(
    row: pd.Series,
    sku_names: Dict[str, str],
) -> str:
    """
    Generate a professional, data-driven recommendation narrative for category
    managers.  Each narrative is tailored to the specific Decision type,
    references actual KPI values, and avoids generic or robotic phrasing.
    """
    dec    = str(row.get("Decision",     "KEEP"))
    sku    = str(row.get("SKU_ID",       ""))
    name   = sku_names.get(sku, sku)
    subcat = str(row.get("Sub_Category", "the sub-category"))
    abc    = str(row.get("ABC_Class",    ""))
    level  = str(row.get("granularity_level", "Global"))
    value  = str(row.get("granularity_value", "Global"))
    h_band = str(row.get("Health_Band",  "MID_HEALTH"))
    f_band = str(row.get("Forecast_Band","FLAT"))
    role   = str(row.get("Basket_Role",  "Solo"))

    hs    = row.get("Health_Score",        np.nan)
    ds    = row.get("delist_score",        np.nan)
    gmroi = row.get("GMROI",              np.nan)
    fg    = row.get("Forecast_Growth_Pct", np.nan)
    msi   = row.get("MarketStrengthIndex", np.nan)
    sent  = row.get("SentimentIndex",      np.nan)
    dep   = float(row.get("basket_dependency_score", 0) or 0)
    sub_s = float(row.get("substitution_score",      0) or 0)
    recap = float(row.get("Recapture_Potential",      0) or 0)

    # Pre-formatted string snippets
    abc_s    = f"{abc}-class " if abc else ""
    scope    = "" if level == "Global" else f" within {level} '{value}'"
    hs_s     = f"{hs:.2f}"     if pd.notna(hs)    else "N/A"
    ds_s     = f"{ds:.2f}"     if pd.notna(ds)    else "N/A"
    fg_s     = f"{fg:+.1f}%"   if pd.notna(fg)    else "unavailable"
    gmroi_s  = f"{gmroi:,.0f}" if pd.notna(gmroi) else "N/A"
    msi_s    = f"{msi:.2f}"    if pd.notna(msi)   else "N/A"
    sent_s   = f"{sent:.2f}"   if pd.notna(sent)  else "N/A"
    dep_n    = int(dep)
    dep_s    = f"{dep_n} co-purchased SKU{'s' if dep_n != 1 else ''}"
    sub_pct  = f"{sub_s:.0%} of same-sub-category peers"
    fb_text  = _FORECAST_BAND_TEXT.get(f_band, f_band.replace("_", " ").lower())

    # ── EXPAND ────────────────────────────────────────────────────────────────
    if dec == "EXPAND":
        return (
            f"{name} is a high-performing {abc_s}SKU in {subcat}{scope}. "
            f"Health score of {hs_s}, GMROI of {gmroi_s}, and forecasted growth "
            f"of {fg_s} demonstrate strong commercial momentum across all key "
            f"dimensions. Market strength index of {msi_s} and customer sentiment "
            f"of {sent_s} further reinforce the case for increased investment. "
            f"Basket linkage to {dep_s} provides category pull. "
            f"Recommend increasing shelf facings, deepening replenishment, and "
            f"expanding distribution to under-indexed locations to capture "
            f"incremental demand."
        )

    # ── FUTURE_STAR ───────────────────────────────────────────────────────────
    if dec == "FUTURE_STAR":
        return (
            f"{name} is an emerging {abc_s}SKU in {subcat}{scope} showing "
            f"early-stage growth indicators that outpace its current commercial "
            f"footprint. Health score of {hs_s} is moderate, but forecast growth "
            f"of {fg_s} signals accelerating momentum. Market strength index "
            f"({msi_s}) and customer sentiment ({sent_s}) are trending positively. "
            f"Delist risk score of {ds_s} remains manageable at this stage. "
            f"Recommend protecting this SKU from premature rationalization and "
            f"selectively increasing visibility to capitalize on the emerging "
            f"growth trajectory before broader rollout."
        )

    # ── KEEP ──────────────────────────────────────────────────────────────────
    if dec == "KEEP":
        return (
            f"{name} is a solid {abc_s}contributor to the {subcat} assortment{scope}. "
            f"Health score of {hs_s}, GMROI of {gmroi_s}, and a {fb_text} ({fg_s}) "
            f"confirm this SKU's core assortment role. Its '{role}' basket position "
            f"— co-purchased alongside {dep_s} — further reinforces retention value. "
            f"No immediate intervention is required. "
            f"Prioritize planogram stability and supply continuity to protect "
            f"consistent consumer availability."
        )

    # ── CASH_COW ──────────────────────────────────────────────────────────────
    if dec == "CASH_COW":
        return (
            f"{name} is a mature {abc_s}SKU in {subcat}{scope} with a "
            f"well-established commercial footprint. Despite a {fb_text} ({fg_s}), "
            f"the SKU delivers GMROI of {gmroi_s} and a health score of {hs_s}, "
            f"indicating sustained profitability even as volume growth plateaus. "
            f"Market strength of {msi_s} and delist score of {ds_s} confirm "
            f"low exit pressure. "
            f"Recommend adopting a harvest strategy: optimize shelf pricing, reduce "
            f"promotional spend, and protect gross margin contribution without "
            f"incremental distribution expansion."
        )

    # ── INVESTIGATE ───────────────────────────────────────────────────────────
    if dec == "INVESTIGATE":
        conflicts: List[str] = []
        fg_val = fg if pd.notna(fg) else 0.0
        if str(row.get("Health_Band")) == "HIGH_HEALTH" and row.get("GMROI_Band") == "LOW_GMROI":
            conflicts.append("strong overall health despite low inventory return (GMROI)")
        if fg_val >= FORECAST_GROWTH_MIN and str(row.get("Delist_Band")) == "HIGH_DELIST":
            conflicts.append("positive growth forecast against elevated delist pressure")
        conflict_str = (
            "; ".join(conflicts) if conflicts else "mixed KPI signals across health, GMROI, and forecast"
        )
        return (
            f"{name} ({abc_s}{subcat}){scope} presents conflicting performance "
            f"signals that require manual category review: {conflict_str}. "
            f"Key metrics — health: {hs_s}, GMROI: {gmroi_s}, forecast growth: {fg_s}, "
            f"market strength: {msi_s} — do not align to a clear commercial decision. "
            f"Standard rule-based classification is insufficient to resolve this "
            f"SKU's status. Recommend escalating to the category review team for a "
            f"structured deep-dive before the next planogram reset."
        )

    # ── KEEP_WATCH ────────────────────────────────────────────────────────────
    if dec == "KEEP_WATCH":
        return (
            f"{name} is a below-average performer in {subcat}{scope}, with a health "
            f"score of {hs_s} and a {fb_text} ({fg_s}). While commercial KPIs are "
            f"under pressure — GMROI of {gmroi_s} and delist score of {ds_s} — the "
            f"SKU's '{role}' basket position (co-purchased alongside {dep_s}) "
            f"provides a near-term justification for retention. "
            f"Immediate delisting is not recommended. "
            f"Set clear performance thresholds for the next review cycle and monitor "
            f"sales velocity, GMROI, and substitution behavior closely before "
            f"committing to further action."
        )

    # ── PHASE_OUT ─────────────────────────────────────────────────────────────
    if dec == "PHASE_OUT":
        return (
            f"{name} is on a declining commercial trajectory in {subcat}{scope}. "
            f"Health score of {hs_s} and forecast growth of {fg_s} indicate "
            f"sustained deterioration that is unlikely to reverse organically. "
            f"GMROI of {gmroi_s} no longer justifies continued full-range support, "
            f"while a delist score of {ds_s} signals growing pressure for "
            f"rationalization. "
            f"Recommend initiating a phased exit: reduce shelf facings by "
            f"approximately 50% at the next planogram reset, discontinue promotional "
            f"support, and notify the supply chain of the planned deactivation "
            f"timeline to minimize write-off exposure."
        )

    # ── REPLACE ───────────────────────────────────────────────────────────────
    if dec == "REPLACE":
        sub_note = (
            f"{sub_pct} qualify as viable in-category substitutes, offering a "
            f"recapture potential of {recap:.0%}"
            if sub_s > 0
            else "limited direct substitutes were identified in basket data — "
                 "verify recapture plan before execution"
        )
        return (
            f"{name} ({abc_s}{subcat}){scope} is a weak commercial performer — "
            f"health score {hs_s}, GMROI {gmroi_s}, forecast growth {fg_s} — but "
            f"category demand recapture is viable: {sub_note}. "
            f"Its '{role}' basket role limits disruption risk. "
            f"Recommend identifying the strongest substitute candidate from the "
            f"demand transfer matrix, staging a controlled shelf space transition, "
            f"and communicating the replacement timeline to the supply chain to "
            f"maintain category continuity and protect customer satisfaction."
        )

    # ── DELIST ────────────────────────────────────────────────────────────────
    sub_note = (
        f"{sub_pct} are confirmed substitutes available to absorb displaced demand"
        if sub_s > 0
        else "limited direct substitutes were identified — verify recapture plan"
    )
    return (
        f"{name} demonstrates weak commercial performance across multiple "
        f"dimensions in {subcat}{scope}: health score {hs_s}, GMROI {gmroi_s}, "
        f"forecast growth {fg_s}, and a delist score of {ds_s}. "
        f"Its '{role}' basket role generates minimal co-purchase dependency, "
        f"and {sub_note}. "
        f"Customer sentiment ({sent_s}) and market strength ({msi_s}) offer no "
        f"mitigating signal strong enough to justify continued assortment inclusion. "
        f"Recommend removing this SKU at the next planogram reset and reallocating "
        f"shelf space and procurement budget toward higher-performing alternatives."
    )


def generate_decision_output(
    df: pd.DataFrame,
    sku_master: pd.DataFrame,
) -> pd.DataFrame:
    """
    Orchestrate the full Advanced Decision Engine pipeline:
      1.  Classify metric bands (Health, Delist, GMROI, Forecast)
      2.  Derive Basket_Role, Recapture_Potential, Cannibalization_Risk
      3.  Apply priority-ordered decision rules → Decision column
      4.  Generate Decision_Reason (concise KPI drivers)
      5.  Generate Recommended_Action (operational instruction)
      6.  Generate Recommendation_Narrative (professional manager-facing text)
      7.  Drop legacy 'recommendation' and 'nl_summary' columns

    This replaces the template-based NL summary with a richer,
    decision-type-specific framework aligned to 9 business decision states.

    Returns enriched DataFrame with legacy columns removed.
    """
    log.info("-" * 50)
    log.info("STEP: Advanced Decision Engine")
    n = len(df)

    # 1 & 2: Bands + basket role + recapture/cannibalization
    df = classify_metric_bands(df)
    log.info(
        f"  Health bands  : {df['Health_Band'].value_counts().to_dict()}"
    )
    log.info(
        f"  Delist bands  : {df['Delist_Band'].value_counts().to_dict()}"
    )
    log.info(
        f"  GMROI bands   : {df['GMROI_Band'].value_counts().to_dict()}"
    )
    log.info(
        f"  Forecast bands: {df['Forecast_Band'].value_counts().to_dict()}"
    )
    log.info(
        f"  Basket roles  : {df['Basket_Role'].value_counts().to_dict()}"
    )

    # 3: Decision assignment (row-wise apply is acceptable given n ≈ 1,260)
    df["Decision"] = df.apply(_apply_single_decision, axis=1)
    decision_counts = df[df["granularity_level"] == "Global"]["Decision"].value_counts()
    log.info(f"  Decision distribution (Global level): {decision_counts.to_dict()}")

    # 4 & 5 & 6: Narrative columns
    sku_names: Dict[str, str] = {}
    if (not sku_master.empty
            and "SKU_ID" in sku_master.columns
            and "Product_Name" in sku_master.columns):
        sku_names = sku_master.set_index("SKU_ID")["Product_Name"].to_dict()

    df["Decision_Reason"]          = df.apply(_build_decision_reason, axis=1)
    df["Recommended_Action"]       = df.apply(_build_recommended_action, axis=1)
    df["Recommendation_Narrative"] = df.apply(
        lambda r: _build_recommendation_narrative(r, sku_names), axis=1
    )
    log.info(f"  [OK] Decision narratives generated for {n:,} rows.")

    # 7: Drop legacy columns — replaced by the new Decision framework
    legacy = [c for c in ["recommendation", "nl_summary"] if c in df.columns]
    if legacy:
        df = df.drop(columns=legacy)
        log.info(f"  Dropped legacy columns: {legacy}")

    # Validate: ensure no new duplicate rows were introduced
    join_keys = ["granularity_level", "granularity_value", "SKU_ID"]
    dup = df.duplicated(subset=join_keys).sum()
    if dup:
        log.warning(f"  {dup} duplicate rows detected after decision engine — deduplicating.")
        df = df.drop_duplicates(subset=join_keys, keep="first").reset_index(drop=True)

    log.info(
        f"  [OK] Advanced Decision Engine complete: "
        f"{len(df):,} rows, {len(df.columns)} columns."
    )
    return df


# =============================================================================
# SECTION 11: MAIN ORCHESTRATION
# =============================================================================

def main() -> None:
    """
    Orchestrate the full basket analysis pipeline:
      1.  Load & validate core inputs
      2.  Build association rules             → association_rules.csv
      3.  Compute SKU basket insights         → sku_basket_insights.csv
      4.  Compute demand transfer matrix      → demand_transfer_matrix.csv
      5.  Compute delist scores               → (in memory)
      6.  Append NL summaries                 → (in memory)
      7.  Load supplemental files             → (in memory)
      8.  Enrich with 12 enhanced KPI columns → (in memory)
      9.  Save enriched output                → delisting_recommendations.csv
    """
    log.info("=" * 60)
    log.info("Basket Analysis & SKU Delisting Recommendation Module")
    log.info("=" * 60)

    try:
        # Step 1: Load core inputs
        tx, sku_master, store_master = load_and_validate()

        # Step 2: Association rules
        rules, item_support, total_baskets = build_association_rules(tx)
        rules.to_csv(RULES_OUT, index=False)
        log.info(f"  [OK] Saved: association_rules.csv  ({len(rules):,} rows)")

        # Step 3: SKU basket insights
        insights = compute_sku_basket_insights(tx, rules, item_support, sku_master)
        insights.to_csv(INSIGHTS_OUT, index=False)
        log.info(f"  [OK] Saved: sku_basket_insights.csv  ({len(insights)} rows)")

        # Step 4: Demand transfer matrix
        transfer = compute_demand_transfer_matrix(tx, rules, sku_master)
        transfer.to_csv(TRANSFER_OUT, index=False)
        log.info(f"  [OK] Saved: demand_transfer_matrix.csv  ({len(transfer):,} rows)")

        # Step 5: Delist scores
        delist_df = compute_delist_scores(tx, insights, rules, sku_master)

        # Step 6: Load supplemental data for enhanced KPIs
        log.info("-" * 50)
        log.info("STEP: Loading supplemental files for enhanced KPI enrichment")
        inv, reviews, market_data, forecast_df = load_supplemental_data()

        # Step 7: Enrich with enhanced KPIs
        delist_df = enrich_with_kpis(
            delist_df, tx, inv, store_master, reviews, market_data, forecast_df,
            sku_master=sku_master,
        )

        # Step 8: Advanced Decision Engine
        # Classifies bands, applies 9-state decision logic, generates narratives,
        # and drops legacy 'recommendation' / 'nl_summary' columns.
        delist_df = generate_decision_output(delist_df, sku_master)

        # Step 9: Save final output
        delist_df.to_csv(DELIST_OUT, index=False)
        log.info(f"  [OK] Saved: delisting_recommendations.csv  ({len(delist_df):,} rows, "
                 f"{len(delist_df.columns)} columns)")

        # ── Final summary ────────────────────────────────────────────────────
        log.info("")
        log.info("=" * 60)
        log.info("RUN COMPLETE - SUMMARY")
        log.info("=" * 60)
        log.info(f"  Baskets analysed:              {total_baskets:,}")
        log.info(f"  Association rules generated:   {len(rules):,}")
        log.info(f"  SKUs with basket insights:     {len(insights)}")
        log.info(f"  Demand transfer pairs:         {len(transfer):,}")
        log.info(f"  Delist recommendation rows:    {len(delist_df):,}")
        log.info(f"  Total output columns:          {len(delist_df.columns)}")
        log.info("")

        global_decisions = (
            delist_df[delist_df["granularity_level"] == "Global"]
            ["Decision"]
            .value_counts()
        )
        log.info("  Global-level Decision breakdown:")
        for dec_label, cnt in global_decisions.items():
            log.info(f"    {dec_label:20s}: {cnt} SKU(s)")

        print_kpi_summary(delist_df)

    except (FileNotFoundError, KeyError, ValueError) as exc:
        log.error(f"FATAL ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
