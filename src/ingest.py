"""
Download NREL ComStock aggregate timeseries data by county and building type
from the public OEDI S3 bucket.

S3 path structure (verified):
  timeseries_aggregates/by_county/upgrade=<id>/county=<GISJOIN>/
    up<id>-<gisjoin_lower>-<building_type>.csv

Requirements:
    python -mpip install boto3 fsspec pandas pyarrow s3fs

Usage:
    python ingest.py

Notes:
    - Energy consumption values are kWh per 15-minute timestep.
    - All timestamps are in U.S. Eastern Standard Time regardless of building location.
    - Check 'models_used' column in each CSV for sample size (low = less reliable).
    - Upgrade IDs change across releases. Use measure_name_crosswalk.csv to map them.
    - For battery sizing POC, upgrade=0 (baseline) is the primary scenario.

Upgrade scenarios (2024 Release 2):
    - Upgrade 0 = Baseline (existing building stock as of 2018)
    - Upgrades 1-26+ = Energy efficiency / electrification measures
      (LED lighting, heat pump RTUs, envelope improvements, etc.)
    - Upgrade IDs are release-specific. Check upgrades_lookup.json or
      measure_name_crosswalk.csv in the dataset for the full mapping.
    - Individual upgrade results should NOT be summed — interactions between
      measures require dedicated package runs (see ComStock documentation).
"""

import os
import boto3
import pandas as pd
from botocore import UNSIGNED
from botocore.config import Config

# =============================================================================
# CONFIGURATION
# =============================================================================

DATASET_YEAR = "2024"
DATASET_NAME = "comstock_amy2018_release_2"

BUCKET = "oedi-data-lake"
BASE_PATH = "nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock"
DATASET_PATH = f"s3://{BUCKET}/{BASE_PATH}/{DATASET_YEAR}/{DATASET_NAME}"

# Upgrade scenarios to download.
# 0 = baseline (existing stock). Add other IDs to download upgrade scenarios.
# Example: [0, 1, 10] downloads baseline + upgrades 1 and 10.
UPGRADE_IDS = [0]

# Counties to download.
# Format must match spatial_tract_lookup_table: "<state_abbrev>, <County Name>"
COUNTIES = [
    {"state": "CO", "county_label": "CO, San Juan County"},
    {"state": "MI", "county_label": "MI, Washtenaw County"},
    {"state": "CA", "county_label": "CA, Orange County"},
]

# Output directory — one level up from this script, in data/raw/
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "raw")

# =============================================================================
# FUNCTIONS
# =============================================================================

def get_county_gisjoin_codes(dataset_path, counties):
    """
    Look up NHGIS GISJOIN codes for each county using the official
    spatial_tract_lookup_table.csv from the dataset.

    Parameters
    ----------
    dataset_path : str
        S3 path to the dataset root
    counties : list of dict
        Each dict has 'state' and 'county_label' keys.

    Returns
    -------
    list of dict
        Input dicts with 'gisjoin' key added (None if not found).
    """
    lookup_path = f"{dataset_path}/geographic_information/spatial_tract_lookup_table.csv"
    print(f"Loading spatial tract lookup table...")
    print(f"  Path: {lookup_path}")

    try:
        lookup = pd.read_csv(lookup_path, low_memory=False)
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

    print(f"  Loaded {len(lookup)} rows\n")

    results = []
    for county in counties:
        label = county["county_label"]
        matches = lookup.loc[
            lookup["resstock_county_id"] == label,
            "nhgis_county_gisjoin"
        ]

        if len(matches) == 0:
            print(f"  WARNING: '{label}' not found in lookup table.")
            similar = lookup["resstock_county_id"].dropna().unique()
            state_prefix = county["state"] + ","
            state_counties = sorted([c for c in similar if c.startswith(state_prefix)])
            if state_counties:
                print(f"  Available counties for {county['state']} (first 10):")
                for sc in state_counties[:10]:
                    print(f"    {sc}")
            results.append({**county, "gisjoin": None})
        else:
            gisjoin = str(matches.iloc[0])
            print(f"  {label} -> GISJOIN: {gisjoin}")
            results.append({**county, "gisjoin": gisjoin})

    return results


def list_s3_objects(s3_client, bucket, prefix):
    """
    List all S3 object keys under a prefix.

    Parameters
    ----------
    s3_client : boto3 S3 client
    bucket : str
    prefix : str

    Returns
    -------
    list of str
        S3 object keys
    """
    keys = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def download_county_upgrade(s3_client, bucket, agg_prefix, upgrade_id, county_info, output_dir):
    """
    Download all aggregate timeseries CSVs for one county + one upgrade scenario.

    S3 path: <agg_prefix>upgrade=<id>/county=<GISJOIN>/<files>.csv

    Parameters
    ----------
    s3_client : boto3 S3 client
    bucket : str
    agg_prefix : str
        Path to timeseries_aggregates/by_county/
    upgrade_id : int
        Upgrade scenario (0 = baseline)
    county_info : dict
        Must have 'state', 'gisjoin', 'county_label' keys
    output_dir : str
        Local directory to save files

    Returns
    -------
    int
        Number of files downloaded
    """
    state = county_info["state"]
    gisjoin = county_info["gisjoin"]

    # S3 prefix: by_county/upgrade=0/county=G0801110/
    prefix = f"{agg_prefix}upgrade={upgrade_id}/county={gisjoin}/"
    county_keys = list_s3_objects(s3_client, bucket, prefix)

    if not county_keys:
        print(f"    No files found (upgrade={upgrade_id})")
        return 0

    print(f"    upgrade={upgrade_id}: {len(county_keys)} building type(s)")

    # Save to: data/raw/<state>_<gisjoin>/upgrade_<id>/
    county_dir = os.path.join(output_dir, f"{state}_{gisjoin}", f"upgrade_{upgrade_id}")
    os.makedirs(county_dir, exist_ok=True)

    downloaded = 0
    for key in sorted(county_keys):
        filename = os.path.basename(key)

        # Extract building type from filename
        # Format: up00-g0801110-fullservicerestaurant.csv
        parts = filename.replace(".csv", "").split("-", 2)
        building_type = parts[2] if len(parts) >= 3 else filename

        local_path = os.path.join(county_dir, filename)

        print(f"      {building_type}")
        try:
            s3_client.download_file(bucket, key, local_path)
            downloaded += 1
        except Exception as e:
            print(f"        ERROR: {e}")

    return downloaded


# =============================================================================
# MAIN
# =============================================================================

def main():
    # Resolve output directory
    output_dir = os.path.normpath(OUTPUT_DIR)
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output directory: {output_dir}\n")

    # Try anonymous access first
    try:
        s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
        s3.list_objects_v2(
            Bucket=BUCKET,
            Prefix=f"{BASE_PATH}/{DATASET_YEAR}/{DATASET_NAME}/",
            MaxKeys=1
        )
        print("Using anonymous S3 access\n")
    except Exception:
        print("Anonymous access failed, using AWS credentials\n")
        s3 = boto3.client("s3")

    # Step 1: Look up GISJOIN codes
    print("--- Step 1: Looking up county GISJOIN codes ---\n")
    counties = get_county_gisjoin_codes(DATASET_PATH, COUNTIES)
    if counties is None:
        print("Failed to load lookup table. Exiting.")
        return

    # Step 2: Download aggregate files for each county x upgrade combination
    print(f"\n--- Step 2: Downloading aggregate files ---")
    print(f"  Upgrades: {UPGRADE_IDS}")
    print(f"  Counties: {[c['county_label'] for c in counties if c.get('gisjoin')]}\n")

    agg_prefix = f"{BASE_PATH}/{DATASET_YEAR}/{DATASET_NAME}/timeseries_aggregates/by_county/"

    total = 0
    for county in counties:
        if county["gisjoin"] is None:
            print(f"  Skipping {county['county_label']} -- GISJOIN not found")
            continue

        print(f"\n  {county['county_label']} ({county['gisjoin']})")
        for upgrade_id in UPGRADE_IDS:
            total += download_county_upgrade(
                s3, BUCKET, agg_prefix, upgrade_id, county, output_dir
            )

    # Summary
    print(f"\n{'='*60}")
    print(f"Done. Downloaded {total} file(s) to {output_dir}")
    print(f"{'='*60}")

    if total > 0:
        print(f"\nFile organization:")
        print(f"  data/raw/")
        print(f"    <state>_<gisjoin>/")
        print(f"      upgrade_0/        <- baseline (existing stock)")
        if len(UPGRADE_IDS) > 1:
            for uid in UPGRADE_IDS[1:]:
                print(f"      upgrade_{uid}/")
        print(f"\nReminders:")
        print(f"  - Energy values are kWh per 15-min timestep")
        print(f"  - Timestamps are U.S. Eastern Standard Time")
        print(f"  - Check 'models_used' column for sample size")
        print(f"  - San Juan County, CO is very small -- expect few models")
        print(f"  - Do NOT sum individual upgrade savings (see ComStock docs)")


if __name__ == "__main__":
    main()
