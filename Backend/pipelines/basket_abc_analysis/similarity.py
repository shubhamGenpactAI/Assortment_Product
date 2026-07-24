"""
similarity.py
=============

Hair Care MVP - New SKU similarity scoring + analog-based demand forecasting.

WHAT THIS SCRIPT DOES
---------------------
1. Loads a SKU master file (Smililarity_SKU.xlsx) describing existing SKUs.
2. Builds FOUR attribute groups (Hierarchy, Functional, Ingredient, Commercial).
3. Compares ONE "new SKU" (from a file if present, else a built-in sample) against
   every existing SKU and produces a similarity score per group:
       - Hierarchy  : one-hot encode categoricals -> cosine similarity
       - Functional : binary flag vectors          -> cosine similarity
       - Ingredient : ingredient sets              -> Jaccard similarity
       - Commercial : one-hot categoricals + scaled numerics -> cosine similarity
4. Combines them into a weighted Final_Similarity_Score (weights configurable below).
5. Writes new_sku_similarity_scores.csv (ranked) and prints the top 10 matches.
6. OPTIONAL: if a demand file exists, estimates analog demand for the new SKU at the
   STORE level (Store_ID x New_SKU_ID x Week) using the top-5 most similar existing
   SKUs' historical store-week demand, and writes new_sku_analog_demand_forecast.csv.

HOW TO RUN
----------
    pip install pandas numpy scikit-learn openpyxl
    python similarity.py

The script runs end-to-end from the current project folder. It auto-detects the
input file, falls back to a sample new SKU if none is provided, and skips the
optional demand step (with a message) if no demand file is found.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import MinMaxScaler

# ===========================================================================
# CONFIGURATION  (everything you might tweak lives here, at the top)
# ===========================================================================
PROJECT_DIR = Path(__file__).resolve().parent
# Repository root (…/Assortment) and its standard data folders. Inputs are
# resolved from these first so the script works against the real project layout
# (Raw_Input/SKU_Master.csv, Outputs/weekly_demand_output.csv); the script's own
# directory is kept as a fallback for legacy standalone use.
REPO_ROOT   = PROJECT_DIR.parents[2]
RAW_DIR     = REPO_ROOT / "Raw_Input"
OUTPUTS_DIR = REPO_ROOT / "Outputs"
# Directories searched (in order) when resolving an input file by candidate name.
SEARCH_DIRS = [RAW_DIR, OUTPUTS_DIR, REPO_ROOT, PROJECT_DIR]

# Candidate names for the SKU master (first one found wins). SKU_Master.csv is
# the canonical project master; the *_Similarity.xlsx names are legacy fallbacks.
SKU_MASTER_CANDIDATES = ["SKU_Master.csv", "Smililarity_SKU.xlsx", "Similarity_SKU.xlsx", "SKU_Master_Similarity.xlsx"]
# Candidate names for an optional "new SKU" input file.
NEW_SKU_CANDIDATES = ["new_sku.csv", "new_sku.xlsx"]
# Candidate demand files for the optional analog-demand step.
DEMAND_CANDIDATES = ["weekly_demand_output.xlsx", "weekly_demand_output.csv", "Forecast_Output.csv"]

OUTPUT_SCORES = OUTPUTS_DIR / "new_sku_similarity_scores.csv"
OUTPUT_ANALOG = OUTPUTS_DIR / "new_sku_analog_demand_forecast.csv"

# --- Weighted similarity weights (must sum to 1.0) ---
WEIGHTS = {
    "hierarchy": 0.35,
    "functional": 0.25,
    "ingredient": 0.20,
    "commercial": 0.20,
}

TOP_N_PRINT = 10   # how many closest SKUs to print
TOP_N_ANALOG = 5   # how many similar SKUs to use for analog demand

# --- Attribute groups (column names AFTER normalization, i.e. spaces->underscores) ---
HIERARCHY_COLS = ["Category", "Sub_Category", "Segment", "Attribute_Claim", "Hair_Type", "Age_Group"]
FUNCTIONAL_COLS = [
    "Sulphate_Free_Flag", "Paraben_Free_Flag", "Organic_Flag",
    "Dandruff_Flag", "Hair_Fall_Flag", "Color_Protection_Flag",
]
INGREDIENT_COLS = ["Ingredient_1", "Ingredient_2", "Ingredient_3", "Ingredient_4"]
COMMERCIAL_CAT_COLS = ["Brand", "Manufacturer", "Ownership", "Price_Band", "Supplier"]
COMMERCIAL_NUM_COLS = ["Pack_Size_ml", "List_Price_USD", "Unit_Cost_USD", "Margin_Pct", "Case_Pack"]

# Identifier / display columns we surface in the output.
ID_COL = "SKU_ID"
DISPLAY_COLS = ["Product_Name", "Brand", "Sub_Category", "Segment", "Attribute_Claim"]

# Built-in fallback new SKU (used only if no new_sku file is found).
SAMPLE_NEW_SKU = {
    "SKU_ID": "NEW_SKU_001",
    "Hair_Type": "All Hair Types",
    "Ingredient_1": "Rosemary",
    "Ingredient_2": "Biotin",
    "Ingredient_3": "Keratin",
    "Ingredient_4": "",
    "Sulphate_Free_Flag": 1,
    "Paraben_Free_Flag": 1,
    "Organic_Flag": 0,
    "Dandruff_Flag": 0,
    "Hair_Fall_Flag": 1,
    "Color_Protection_Flag": 0,
    "Product_Name": "Sample Rosemary Biotin Anti Hair Fall Shampoo 300ml",
    "Brand": "SampleBrand",
    "Manufacturer": "SampleManufacturer",
    "Ownership": "Private Label",
    "Category": "Hair Care",
    "Sub_Category": "Shampoo",
    "Segment": "Anti Hair Fall",
    "Attribute_Claim": "Rosemary Biotin",
    "Pack_Size_ml": 300,
    "Price_Band": "Premium",
    "Supplier": "SampleSupplier",
    "List_Price_USD": 8.99,
    "Unit_Cost_USD": 4.25,
    "Margin_Pct": 52.7,
    "Case_Pack": 12,
    "Launch_Date": "2026-01-01",
    "Status": "New",
    "Age Group": "Adult",   # note the space; normalize_column_names handles it
}


# ===========================================================================
# 1. FILE DISCOVERY
# ===========================================================================
def find_input_file(candidates):
    """
    Return the first existing file (Path) for the given candidate names, searching
    each of SEARCH_DIRS (Raw_Input, Outputs, repo root, then the script's own
    directory) in order. Candidate-name priority wins over directory order.
    """
    for name in candidates:
        for base in SEARCH_DIRS:
            p = base / name
            if p.exists():
                return p
    return None


# ===========================================================================
# 2. LOAD SKU MASTER
# ===========================================================================
def load_sku_master():
    """
    Locate and read the SKU master file (Excel or CSV). Raises a clear error if no
    master file is found or if it is empty.
    """
    path = find_input_file(SKU_MASTER_CANDIDATES)
    if path is None:
        raise FileNotFoundError(
            f"SKU master file not found. Looked for: {SKU_MASTER_CANDIDATES} in {PROJECT_DIR}"
        )
    df = pd.read_excel(path) if path.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(path)
    if df.empty:
        raise ValueError(f"SKU master file '{path.name}' contains no rows.")
    print(f"[load_sku_master] Loaded {len(df)} SKUs from {path.name}")
    return df


# ===========================================================================
# 3. NORMALIZE COLUMN NAMES
# ===========================================================================
def normalize_column_names(df):
    """
    Standardize column names so the master file and the new-SKU dict line up.

    We trim whitespace and convert internal spaces to underscores. This reconciles
    the prompt's 'Age Group' (space) with the file's actual 'Age_Group' (underscore),
    so downstream code can rely on a single canonical spelling.
    """
    df = df.copy()
    df.columns = [str(c).strip().replace(" ", "_") for c in df.columns]
    return df


def _normalize_keys(d):
    """Apply the same name normalization to a plain dict (the new SKU)."""
    return {str(k).strip().replace(" ", "_"): v for k, v in d.items()}


# ===========================================================================
# Helpers: binary-flag coercion & ingredient sets
# ===========================================================================
def _to_binary(value):
    """
    Coerce a flag value to 0/1.

    The master stores flags as 'Yes'/'No' strings while the sample new SKU uses
    1/0 integers; this helper accepts both (plus True/False, Y/N) so functional
    comparison works regardless of source format.
    """
    if pd.isna(value):
        return 0
    s = str(value).strip().lower()
    return 1 if s in {"1", "yes", "y", "true", "t"} else 0


def _ingredient_set(row):
    """Build a clean, lower-cased set of non-empty ingredients from Ingredient_1..4."""
    items = set()
    for col in INGREDIENT_COLS:
        val = row.get(col, "")
        if pd.notna(val) and str(val).strip() != "":
            items.add(str(val).strip().lower())
    return items


# ===========================================================================
# 4. VALIDATE SKU MASTER
# ===========================================================================
def validate_sku_master(df):
    """
    Run data-quality checks and collect issues into a summary dict (printed later).

    Checks: required columns present, duplicate SKU_IDs, empty ingredient rows,
    and non-numeric values in numeric commercial fields.
    """
    issues = {}

    required = (
        [ID_COL] + HIERARCHY_COLS + FUNCTIONAL_COLS + INGREDIENT_COLS
        + COMMERCIAL_CAT_COLS + COMMERCIAL_NUM_COLS + DISPLAY_COLS
    )
    missing = sorted(set(c for c in required if c not in df.columns))
    issues["missing_required_columns"] = missing

    if ID_COL in df.columns:
        dupes = df[ID_COL][df[ID_COL].duplicated()].unique().tolist()
        issues["duplicate_sku_ids"] = dupes
    else:
        issues["duplicate_sku_ids"] = ["<SKU_ID column missing>"]

    # Rows where every ingredient field is empty.
    empty_ing = 0
    for _, r in df.iterrows():
        if len(_ingredient_set(r)) == 0:
            empty_ing += 1
    issues["rows_with_no_ingredients"] = empty_ing

    # Numeric columns that fail conversion.
    bad_numeric = {}
    for col in COMMERCIAL_NUM_COLS:
        if col in df.columns:
            n_bad = pd.to_numeric(df[col], errors="coerce").isna().sum() - df[col].isna().sum()
            if n_bad > 0:
                bad_numeric[col] = int(n_bad)
    issues["invalid_numeric_values"] = bad_numeric

    return issues


# ===========================================================================
# 5. LOAD NEW SKU
# ===========================================================================
def load_new_sku():
    """
    Load the new SKU either from a file (new_sku.csv / new_sku.xlsx, first row) or,
    if none exists, from the built-in SAMPLE_NEW_SKU dictionary. Returns a dict with
    normalized keys plus a flag indicating the source.
    """
    path = find_input_file(NEW_SKU_CANDIDATES)
    if path is not None:
        df = pd.read_excel(path) if path.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(path)
        if df.empty:
            raise ValueError(f"New SKU file '{path.name}' is empty.")
        new_sku = df.iloc[0].to_dict()
        print(f"[load_new_sku] Loaded new SKU from {path.name}")
        return _normalize_keys(new_sku), path.name

    print("[load_new_sku] No new_sku file found -> using built-in SAMPLE_NEW_SKU.")
    return _normalize_keys(SAMPLE_NEW_SKU), "SAMPLE_NEW_SKU (hardcoded)"


def validate_new_sku(new_sku):
    """Report which expected attribute fields are missing/blank in the new SKU."""
    expected = HIERARCHY_COLS + FUNCTIONAL_COLS + INGREDIENT_COLS + COMMERCIAL_CAT_COLS + COMMERCIAL_NUM_COLS
    missing = [c for c in expected if c not in new_sku or pd.isna(new_sku.get(c)) or str(new_sku.get(c)).strip() == ""]
    return missing


# ===========================================================================
# 6. BUILD ATTRIBUTE MATRIX
# ===========================================================================
def build_attribute_matrix(existing_df, new_sku):
    """
    Stack existing SKUs + the new SKU into one DataFrame so that any encoding
    (one-hot, scaling) is fit over BOTH and produces aligned feature columns.

    The new SKU is always the LAST row. Missing columns in the new SKU are added
    as blanks so the schemas match.
    """
    new_row = {col: new_sku.get(col, np.nan) for col in existing_df.columns}
    # Ensure SKU_ID is present even if not in master columns ordering.
    new_row[ID_COL] = new_sku.get(ID_COL, "NEW_SKU")
    combined = pd.concat([existing_df, pd.DataFrame([new_row])], ignore_index=True)
    return combined


def _cosine_new_vs_existing(matrix):
    """
    Given a feature matrix where the LAST row is the new SKU, return cosine
    similarity of the new SKU against each existing row (length = n_existing).
    sklearn returns 0 for zero-norm vectors (safe, no NaN).
    """
    new_vec = matrix[-1].reshape(1, -1)
    existing = matrix[:-1]
    sims = cosine_similarity(new_vec, existing)[0]
    return sims


# ===========================================================================
# 7. SIMILARITY CALCULATIONS (one per attribute group)
# ===========================================================================
def calculate_hierarchy_similarity(combined):
    """
    Hierarchy similarity: one-hot encode the merchandising hierarchy fields, then
    cosine-similarity the new SKU against each existing SKU. Categorical values are
    cast to string and blanks become an explicit 'MISSING' category.
    """
    cols = [c for c in HIERARCHY_COLS if c in combined.columns]
    cat = combined[cols].astype(str).replace({"nan": "MISSING", "": "MISSING"})
    encoded = pd.get_dummies(cat).to_numpy(dtype=float)
    return _cosine_new_vs_existing(encoded)


def calculate_functional_similarity(combined):
    """
    Functional similarity: convert the six benefit flags to a 0/1 binary vector and
    use cosine similarity. Cosine on binary vectors rewards shared 'on' flags.
    """
    cols = [c for c in FUNCTIONAL_COLS if c in combined.columns]
    binary = combined[cols].apply(lambda col: col.map(_to_binary)).to_numpy(dtype=float)
    return _cosine_new_vs_existing(binary)


def calculate_ingredient_similarity(combined):
    """
    Ingredient similarity: treat Ingredient_1..4 as a SET and use Jaccard:
        |intersection| / |union|.
    Example: {Keratin,Biotin,Argan Oil} vs {Keratin,Rosemary} -> 1/4 = 0.25.
    If both sets are empty (no usable ingredients) similarity is 0.
    """
    sets = combined.apply(_ingredient_set, axis=1).tolist()
    new_set = sets[-1]
    sims = []
    for s in sets[:-1]:
        union = new_set | s
        sims.append(len(new_set & s) / len(union) if union else 0.0)
    return np.array(sims, dtype=float)


def calculate_commercial_similarity(combined):
    """
    Commercial similarity: mixed encoding.
      * One-hot encode categorical fields (Brand, Manufacturer, Ownership,
        Price_Band, Supplier).
      * Min-max scale numeric fields (Pack_Size_ml, List_Price_USD, Unit_Cost_USD,
        Margin_Pct, Case_Pack) to [0,1] so no single large-magnitude field dominates.
      * Concatenate both blocks and use cosine similarity.
    Scaling is fit over existing + new together so the new SKU sits on the same scale.
    """
    cat_cols = [c for c in COMMERCIAL_CAT_COLS if c in combined.columns]
    num_cols = [c for c in COMMERCIAL_NUM_COLS if c in combined.columns]

    cat = combined[cat_cols].astype(str).replace({"nan": "MISSING", "": "MISSING"})
    cat_encoded = pd.get_dummies(cat).to_numpy(dtype=float)

    num = combined[num_cols].apply(pd.to_numeric, errors="coerce")
    num = num.fillna(num.median(numeric_only=True)).fillna(0)  # impute bad/missing numerics
    num_scaled = MinMaxScaler().fit_transform(num) if num.shape[1] else np.empty((len(combined), 0))

    matrix = np.hstack([cat_encoded, num_scaled])
    return _cosine_new_vs_existing(matrix)


# ===========================================================================
# 8. WEIGHTED COMBINATION
# ===========================================================================
def calculate_weighted_similarity(hier, func, ingr, comm):
    """
    Combine the four group scores into the final score using the configured weights.
    All inputs are clipped to [0,1] for safety before weighting.
    """
    hier = np.clip(hier, 0, 1)
    func = np.clip(func, 0, 1)
    ingr = np.clip(ingr, 0, 1)
    comm = np.clip(comm, 0, 1)
    final = (
        WEIGHTS["hierarchy"] * hier
        + WEIGHTS["functional"] * func
        + WEIGHTS["ingredient"] * ingr
        + WEIGHTS["commercial"] * comm
    )
    return hier, func, ingr, comm, np.clip(final, 0, 1)


# ===========================================================================
# 9. OUTPUT TABLE
# ===========================================================================
def generate_similarity_output(existing_df, new_sku, hier, func, ingr, comm, final):
    """
    Assemble the ranked output DataFrame with the required columns, sorted by
    Final_Similarity_Score descending, and write it to CSV.
    """
    out = pd.DataFrame({
        "New_SKU_ID": new_sku.get(ID_COL, "NEW_SKU"),
        "Existing_SKU_ID": existing_df[ID_COL].values,
        "Existing_Product_Name": existing_df.get("Product_Name", pd.Series([""] * len(existing_df))).values,
        "Existing_Brand": existing_df.get("Brand", pd.Series([""] * len(existing_df))).values,
        "Existing_Sub_Category": existing_df.get("Sub_Category", pd.Series([""] * len(existing_df))).values,
        "Existing_Segment": existing_df.get("Segment", pd.Series([""] * len(existing_df))).values,
        "Existing_Attribute_Claim": existing_df.get("Attribute_Claim", pd.Series([""] * len(existing_df))).values,
        "Hierarchy_Similarity": np.round(hier, 4),
        "Functional_Similarity": np.round(func, 4),
        "Ingredient_Similarity": np.round(ingr, 4),
        "Commercial_Similarity": np.round(comm, 4),
        "Final_Similarity_Score": np.round(final, 4),
    })
    out = out.sort_values("Final_Similarity_Score", ascending=False).reset_index(drop=True)
    out["Similarity_Rank"] = out.index + 1  # 1 = most similar
    out.to_csv(OUTPUT_SCORES, index=False)
    print(f"[generate_similarity_output] Wrote {OUTPUT_SCORES.name}")
    return out


# ===========================================================================
# 10. OPTIONAL ANALOG DEMAND
# ===========================================================================
def generate_optional_analog_forecast(scores_df):
    """
    STORE-LEVEL analog demand forecast.

    Business rationale
    ------------------
    Historical demand for existing SKUs lives at Store_ID x SKU_ID x Week. A new
    SKU will be stocked and sold per store, so its demand must be projected at the
    SAME grain -- Store_ID x New_SKU_ID x Week -- rather than collapsed into one
    national/category number. Different stores carry different analog SKUs and sell
    at different volumes, so a store-level analog preserves that local signal.

    Method (per Store_ID x Week)
    ----------------------------
      * Take the top-N most similar existing SKUs (analogs) and their similarity
        scores.
      * Similarity_Weight = Final_Similarity_Score / sum(top-N scores).
      * For each Store_ID x Week, compute a similarity-weighted demand using only
        the analog SKUs actually present in that store/week, then RENORMALIZE by
        the weight of the present analogs:

            Analog_Demand[store, week] =
                sum_over_present_analogs( weight_sku * Quantity[store, sku, week] )
                / sum_over_present_analogs( weight_sku )

        Renormalization makes the result a proper weighted average, so a store that
        only carries some of the analog SKUs is not understated.

    Output: new_sku_analog_demand_forecast.csv at Store_ID x New_SKU_ID x Week.
    If no demand file exists, prints a message and skips (returns None).
    """
    demand_path = find_input_file(DEMAND_CANDIDATES)
    if demand_path is None:
        print("[analog] No demand file found -> skipping store-level analog demand step.")
        return None

    demand = (
        pd.read_excel(demand_path)
        if demand_path.suffix.lower() in (".xlsx", ".xls")
        else pd.read_csv(demand_path)
    )

    # The store-level grain REQUIRES a Store_ID, a SKU_ID, a week, and a quantity.
    # Detect the week/quantity columns so we can also consume Forecast_Output.csv
    # (Forecast_Week / Final_Forecast) as well as weekly_demand_output (Year_WK /
    # Quantity_Sold).
    week_col = next((c for c in ["Year_WK", "Forecast_Week", "Week"] if c in demand.columns), None)
    qty_col = next((c for c in ["Quantity_Sold", "Final_Forecast", "Quantity"] if c in demand.columns), None)
    missing = [name for name, col in
               [("Store_ID", "Store_ID" if "Store_ID" in demand.columns else None),
                ("SKU_ID", "SKU_ID" if "SKU_ID" in demand.columns else None),
                ("week", week_col), ("quantity", qty_col)] if col is None]
    if missing:
        print(f"[analog] '{demand_path.name}' lacks required field(s) for store-level "
              f"forecasting: {missing} -> skipping.")
        return None

    new_sku_id = scores_df["New_SKU_ID"].iloc[0]

    # --- Top-N analog SKUs and their (global) similarity weights ---
    top = scores_df.head(TOP_N_ANALOG).copy()
    weight_total = top["Final_Similarity_Score"].sum()
    if weight_total <= 0:
        print("[analog] Top-N similarity weights sum to 0 -> cannot compute analog demand. Skipping.")
        return None
    top["Similarity_Weight"] = top["Final_Similarity_Score"] / weight_total
    weight_map = dict(zip(top["Existing_SKU_ID"], top["Similarity_Weight"]))
    analog_ids = list(weight_map.keys())

    # --- Keep only the analog SKUs' historical demand rows ---
    d = demand[demand["SKU_ID"].isin(analog_ids)].copy()
    if d.empty:
        print("[analog] None of the top analog SKUs appear in the demand file -> skipping.")
        return None
    d[qty_col] = pd.to_numeric(d[qty_col], errors="coerce").fillna(0)
    d["sim_weight"] = d["SKU_ID"].map(weight_map)
    d["weighted_qty"] = d["sim_weight"] * d[qty_col]

    # --- Aggregate to Store_ID x Week, renormalizing by present analog weight ---
    grouped = d.groupby(["Store_ID", week_col]).agg(
        weighted_sum=("weighted_qty", "sum"),
        present_weight=("sim_weight", "sum"),
        analog_skus_used=("SKU_ID", "nunique"),
    ).reset_index()
    grouped["Analog_Demand"] = (grouped["weighted_sum"] / grouped["present_weight"]).round(2)

    # --- Assemble the Store_ID x New_SKU_ID x Week output ---
    out = pd.DataFrame({
        "New_SKU_ID": new_sku_id,
        "Store_ID": grouped["Store_ID"],
        "Year_WK": grouped[week_col],
        "Analog_Demand": grouped["Analog_Demand"],
        "Analog_SKUs_Used": grouped["analog_skus_used"],
    }).sort_values(["Store_ID", "Year_WK"]).reset_index(drop=True)

    out.to_csv(OUTPUT_ANALOG, index=False)

    print(f"[analog] Store-level analog demand built from top {len(analog_ids)} SKUs "
          f"(source: {demand_path.name}).")
    print(f"[analog] Grain: Store_ID x New_SKU_ID x Week | "
          f"rows={len(out)}, stores={out['Store_ID'].nunique()}, weeks={out['Year_WK'].nunique()}")
    print(f"[analog] Wrote {OUTPUT_ANALOG.name}")
    return out


# ===========================================================================
# MAIN
# ===========================================================================
def main():
    """Run the full pipeline end-to-end."""
    print("=" * 60)
    print("NEW SKU SIMILARITY SCORING")
    print("=" * 60)

    # --- Sanity check: weights must sum to 1.0 ---
    if not np.isclose(sum(WEIGHTS.values()), 1.0):
        raise ValueError(f"WEIGHTS must sum to 1.0; got {sum(WEIGHTS.values())}")

    # 1) Load + normalize the SKU master.
    master = normalize_column_names(load_sku_master())

    # 2) Validate the master and the new SKU.
    master_issues = validate_sku_master(master)
    new_sku, new_sku_source = load_new_sku()
    new_sku_missing = validate_new_sku(new_sku)

    # Drop duplicate SKU_IDs (keep first) so each existing SKU appears once.
    if ID_COL in master.columns and master[ID_COL].duplicated().any():
        master = master.drop_duplicates(subset=[ID_COL], keep="first").reset_index(drop=True)

    # 3) Build the combined matrix (existing + new SKU as last row).
    combined = build_attribute_matrix(master, new_sku)

    # 4) Compute the four group similarities.
    hier = calculate_hierarchy_similarity(combined)
    func = calculate_functional_similarity(combined)
    ingr = calculate_ingredient_similarity(combined)
    comm = calculate_commercial_similarity(combined)

    # 5) Weighted combination.
    hier, func, ingr, comm, final = calculate_weighted_similarity(hier, func, ingr, comm)

    # 6) Range validation (all scores must lie in [0,1]).
    out_of_range = sum(
        int(((arr < 0) | (arr > 1)).any())
        for arr in (hier, func, ingr, comm, final)
    )

    # 7) Build + save the ranked output.
    scores_df = generate_similarity_output(master, new_sku, hier, func, ingr, comm, final)

    # 8) Optional analog demand.
    generate_optional_analog_forecast(scores_df)

    # ---- Validation summary ----
    print("\n" + "-" * 60)
    print("VALIDATION SUMMARY")
    print("-" * 60)
    print(f"New SKU source                 : {new_sku_source}")
    print(f"Existing SKUs scored           : {len(scores_df)}")
    print(f"Missing required columns       : {master_issues['missing_required_columns'] or 'none'}")
    print(f"Duplicate SKU_IDs in master    : {master_issues['duplicate_sku_ids'] or 'none'}")
    print(f"Master rows with no ingredients: {master_issues['rows_with_no_ingredients']}")
    print(f"Invalid numeric values         : {master_issues['invalid_numeric_values'] or 'none'}")
    print(f"Missing new-SKU fields         : {new_sku_missing or 'none'}")
    print(f"Score groups out of [0,1] range: {out_of_range}")

    # ---- Top matches ----
    print("\n" + "-" * 60)
    print(f"TOP {TOP_N_PRINT} CLOSEST EXISTING SKUs")
    print("-" * 60)
    cols = ["Similarity_Rank", "Existing_SKU_ID", "Existing_Product_Name", "Final_Similarity_Score"]
    print(scores_df[cols].head(TOP_N_PRINT).to_string(index=False))
    print(f"\nFull results: {OUTPUT_SCORES}")


if __name__ == "__main__":
    main()
