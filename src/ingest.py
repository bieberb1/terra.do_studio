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
 
Upgrade scenarios (2024 Release 2):
    - Upgrade 0 = Baseline (existing building stock as of 2018)
    - Upgrade 36 = Package 3: LED Lighting + HP-RTU Standard Performance + ASHP Boiler
    - Upgrades 1-26+ = Other energy efficiency / electrification measures
    - Check upgrades_lookup.json (downloaded to data/raw/) for the full mapping.
    - Individual upgrade results should NOT be summed (see ComStock documentation).
"""
 
import os
import json
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
# 0  = baseline (existing stock)
# 36 = Package 3: LED Lighting + HP-RTU Standard Performance + ASHP Boiler
UPGRADE_IDS = [0, 36]
 
# Counties to download.
# Format must match spatial_tract_lookup_table: "<state_abbrev>, <County Name>"
COUNTIES = [
    {"state": "CO", "county_label": "CO, Denver County"},
    {"state": "MI", "county_label": "MI, Washtenaw County"},
    {"state": "CA", "county_label": "CA, Orange County"},
]
 
# Output directory
OUTPUT_DIR = os.path.join(".", "data", "raw")
 
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
 
 
def download_upgrades_lookup(s3_client, bucket, base_path, dataset_year, dataset_name, output_dir):
    """
    Download the upgrades_lookup.json file to help identify upgrade IDs.
 
    Parameters
    ----------
    s3_client : boto3 S3 client
    bucket : str
    base_path : str
    dataset_year : str
    dataset_name : str
    output_dir : str
 
    Returns
    -------
    dict or None
        Parsed JSON contents, or None if download failed.
    """
    key = f"{base_path}/{dataset_year}/{dataset_name}/upgrades_lookup.json"
    local_path = os.path.join(output_dir, "upgrades_lookup.json")
 
    print(f"Downloading upgrades_lookup.json...")
    try:
        s3_client.download_file(bucket, key, local_path)
        with open(local_path, "r") as f:
            data = json.load(f)
        print(f"  Saved to {local_path}")
        print(f"  {len(data)} upgrade(s) defined\n")
 
        # Print a summary of available upgrades
        print("  Available upgrades:")
        for uid, info in sorted(data.items(), key=lambda x: int(x[0])):
            # The structure varies; try to extract a name
            if isinstance(info, dict):
                name = info.get("upgrade_name", info.get("name", str(info)))
            else:
                name = str(info)
            # Truncate long names
            if len(name) > 80:
                name = name[:77] + "..."
            print(f"    {uid}: {name}")
        print()
 
        return data
    except Exception as e:
        print(f"  Could not download upgrades_lookup.json: {e}")
        print(f"  Continuing without it.\n")
        return None
 
 
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
 
    # Step 1: Download upgrades lookup
    print("--- Step 1: Downloading upgrade definitions ---\n")
    download_upgrades_lookup(s3, BUCKET, BASE_PATH, DATASET_YEAR, DATASET_NAME, output_dir)
 
    # Step 2: Look up GISJOIN codes
    print("--- Step 2: Looking up county GISJOIN codes ---\n")
    counties = get_county_gisjoin_codes(DATASET_PATH, COUNTIES)
    if counties is None:
        print("Failed to load lookup table. Exiting.")
        return
 
    # Step 3: Download aggregate files for each county x upgrade combination
    print(f"\n--- Step 3: Downloading aggregate files ---")
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
        print(f"    upgrades_lookup.json  <- upgrade ID definitions")
        print(f"    <state>_<gisjoin>/")
        for uid in UPGRADE_IDS:
            label = "baseline" if uid == 0 else f"upgrade scenario"
            print(f"      upgrade_{uid}/        <- {label}")
        print(f"\nReminders:")
        print(f"  - Energy values are kWh per 15-min timestep (summed across all buildings)")
        print(f"  - Timestamps are U.S. Eastern Standard Time")
        print(f"  - Check 'models_used' column for sample size")
        print(f"  - Do NOT sum individual upgrade savings (see ComStock docs)")
 
 
if __name__ == "__main__":
    main()