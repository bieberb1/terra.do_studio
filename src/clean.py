"""
Combine raw ComStock CSV files and produce cleaned output files.

Reads all CSVs from data/raw/<STATE>_<GISJOIN>/upgrade_<id>/*.csv,
adds a 'state' column derived from the folder name, normalises all energy
consumption columns to kWh per 1000 square feet by dividing by
floor_area_represented, and writes:

    data/processed/combined.csv       — all timesteps, all upgrades
    data/processed/combined_dec1_3.csv — December 1–3 only

Retained columns: state, upgrade, in.county, in.comstock_building_type,
timestamp, floor_area_represented, plus all energy intensity columns
(kwh_per_1000sqft).  The 'upgrade' column carries the scenario ID from
the raw CSV (0 = baseline, 36 = Package 3).

Normalisation note
------------------
floor_area_represented is constant within each county × building-type file
(verified: nunique == 1 per file, no zeros, no nulls).  Each out.* column
is divided by that constant and multiplied by 1000 to produce energy
intensity in kWh/1000 sqft per 15-min interval.  Column names are renamed
from *.kwh to *.kwh_per_1000sqft.
"""

import os
import sys
import glob

import pandas as pd

# =============================================================================
# PATHS
# =============================================================================

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.normpath(os.path.join(SRC_DIR, "..", "data", "raw"))
PROCESSED_DIR = os.path.normpath(os.path.join(SRC_DIR, "..", "data", "processed"))

OUTPUT_ALL = os.path.join(PROCESSED_DIR, "combined.csv")
OUTPUT_DEC = os.path.join(PROCESSED_DIR, "combined_dec1_3.csv")

# Columns to retain (plus floor_area_represented and all out.* energy columns)
ID_COLS = ["state", "upgrade", "in.county", "in.comstock_building_type", "timestamp"]
FLOOR_AREA_COL = "floor_area_represented"

# December 1–3 filter (inclusive, any year)
DEC_START_MMDD = (12, 1)
DEC_END_MMDD = (12, 3)

# =============================================================================
# HELPERS
# =============================================================================


def parse_state_from_folder(folder_name: str) -> str:
    """Extract two-letter state abbreviation from folder names like 'CO_G0801110'."""
    return folder_name.split("_")[0]


def load_csv(path: str, state: str) -> pd.DataFrame:
    """
    Load one raw CSV, inject a 'state' column, and return it.
    Raises if required columns are missing.
    """
    df = pd.read_csv(path, low_memory=False)

    required = {"in.county", "in.comstock_building_type", "timestamp", FLOOR_AREA_COL}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns {missing} in {path}")

    df.insert(0, "state", state)
    return df


# =============================================================================
# MAIN
# =============================================================================


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Discover all CSV files
    # ------------------------------------------------------------------
    pattern = os.path.join(RAW_DIR, "**", "*.csv")
    csv_paths = sorted(glob.glob(pattern, recursive=True))

    if not csv_paths:
        print(f"ERROR: No CSV files found under {RAW_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(csv_paths)} CSV file(s) under {RAW_DIR}")

    # ------------------------------------------------------------------
    # 2. Load and concatenate
    # ------------------------------------------------------------------
    frames = []
    for path in csv_paths:
        # Folder immediately under RAW_DIR encodes the state
        rel = os.path.relpath(path, RAW_DIR)
        top_folder = rel.split(os.sep)[0]          # e.g. "CO_G0801110"
        state = parse_state_from_folder(top_folder)

        df = load_csv(path, state)
        frames.append(df)
        print(f"  Loaded {path}")
        print(f"    shape: {df.shape}  nulls: {df.isnull().sum().sum()}")

    combined = pd.concat(frames, ignore_index=True)
    print(f"\nCombined shape: {combined.shape}")
    print(f"Null counts per column:\n{combined.isnull().sum()}\n")

    # ------------------------------------------------------------------
    # 3. Parse timestamp and select columns
    # ------------------------------------------------------------------
    combined["timestamp"] = pd.to_datetime(combined["timestamp"])

    # Exclude *.savings columns from upgrade_36 — keep only base energy columns
    energy_cols = [c for c in combined.columns if c.startswith("out.") and not c.endswith(".savings")]
    keep_cols = ID_COLS + [FLOOR_AREA_COL] + energy_cols
    missing_keep = [c for c in keep_cols if c not in combined.columns]
    if missing_keep:
        raise ValueError(f"Expected columns not found in combined data: {missing_keep}")

    combined = combined[keep_cols]
    print(f"Retained {len(keep_cols)} columns ({len(energy_cols)} energy columns)\n")

    # ------------------------------------------------------------------
    # 3a. Normalise energy columns to kWh per square foot
    # ------------------------------------------------------------------
    # Validate floor_area_represented: must be positive and non-null
    fa = combined[FLOOR_AREA_COL]
    null_fa = fa.isnull().sum()
    zero_fa = (fa == 0).sum()
    if null_fa > 0:
        raise ValueError(f"{null_fa} null values in {FLOOR_AREA_COL} — cannot normalise.")
    if zero_fa > 0:
        raise ValueError(f"{zero_fa} zero values in {FLOOR_AREA_COL} — cannot divide.")

    combined[energy_cols] = combined[energy_cols].div(combined[FLOOR_AREA_COL], axis=0) * 1000

    # Rename *.kwh columns to *.kwh_per_1000sqft to reflect the new unit
    rename_map = {c: c.replace(".kwh", ".kwh_per_1000sqft") for c in energy_cols if c.endswith(".kwh")}
    combined.rename(columns=rename_map, inplace=True)
    energy_cols = [rename_map.get(c, c) for c in energy_cols]

    print(f"Normalised {len(rename_map)} energy columns by {FLOOR_AREA_COL} (kWh -> kWh/1000sqft)")
    print("  Sample floor areas (first row per group):")
    sample = combined.groupby(["state", "upgrade", "in.comstock_building_type"])[FLOOR_AREA_COL].first()
    for (state, upgrade, btype), val in sample.items():
        print(f"    {state} upgrade={upgrade} {btype}: {val:,.0f} sqft")
    print()

    # ------------------------------------------------------------------
    # 4. Write combined output
    # ------------------------------------------------------------------
    combined.to_csv(OUTPUT_ALL, index=False)
    print(f"Wrote combined output  -> {OUTPUT_ALL}  ({len(combined):,} rows)")

    # ------------------------------------------------------------------
    # 5. Filter to December 1–3 and write
    # ------------------------------------------------------------------
    mask = (
        (combined["timestamp"].dt.month == 12)
        & (combined["timestamp"].dt.day >= DEC_START_MMDD[1])
        & (combined["timestamp"].dt.day <= DEC_END_MMDD[1])
    )
    dec = combined.loc[mask].copy()

    print(f"\nDecember 1–3 filter: {len(dec):,} rows")
    print(f"Null counts in filtered data:\n{dec.isnull().sum()}\n")

    if dec.empty:
        print("WARNING: December 1–3 filter returned no rows. Check timestamp format/year.")

    dec.to_csv(OUTPUT_DEC, index=False)
    print(f"Wrote December 1–3 output -> {OUTPUT_DEC}  ({len(dec):,} rows)")


if __name__ == "__main__":
    main()
