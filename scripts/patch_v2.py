# -*- coding: utf-8 -*-
"""
patch_v2.py — Backfill precision tiers and fix provenance on the v2 enriched dataset.

Usage:
    python scripts/patch_v2.py input.xlsx output.xlsx

See POLICY.md for the full rationale and tier rules.
"""

import sys
import os
import pandas as pd
import numpy as np

# Ensure app modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import enrich_pipeline as ep

PRECISION_COL = "דיוק_גאוקוד"
METHOD_COL = "geocode_method"
LAT_COL = "קו_רוחב"
LON_COL = "קו_אורך"

# Methods that indicate the row was manually backfilled (had coords but wrong label)
_RELABEL_METHODS = {"unresolved", "flagged_description", "no_street"}

# Methods that map directly to a precision tier (when not collapsed)
_METHOD_TO_TIER = {
    "gis_exact":           "address",
    "gis_nearest":         "near_address",
    "gis_centroid":        "street",
    "street_centroid_osm": "street",
    "gis_intersection":    "street",
    "osm_centroid":        "street",
    "manual":              "address",
    "manual_backfilled":   "address",
}

COLLAPSE_MIN_ROWS = 5
COLLAPSE_MIN_DISTINCT_HOUSES = 4


def _coerce_coords(df: pd.DataFrame) -> pd.DataFrame:
    """Strip trailing commas and coerce coordinate columns to float64."""
    for col in (LAT_COL, LON_COL):
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "").str.strip(),
                errors="coerce",
            )
    return df


def _relabel_methods(df: pd.DataFrame) -> pd.DataFrame:
    """Relabel coordinate-bearing rows with broken method labels."""
    has_coords = df[LAT_COL].notna() & df[LON_COL].notna()
    bad_method = df[METHOD_COL].isin(_RELABEL_METHODS)
    df.loc[has_coords & bad_method, METHOD_COL] = "manual_backfilled"
    return df


def _find_collapsed_coords(df: pd.DataFrame) -> set:
    """
    Identify coordinate pairs shared by ≥ COLLAPSE_MIN_ROWS rows spanning
    ≥ COLLAPSE_MIN_DISTINCT_HOUSES distinct house numbers.

    Exclusions from the distinct-house count:
      - NaN / blank / "0" house numbers
      - Rows with סוג_מיקום == "טווח בתים"
      - Rows with סוג_מיקום == "ציון דרך"
    """
    has_coords = df[LAT_COL].notna() & df[LON_COL].notna()
    sub = df[has_coords].copy()
    sub["_coord_key"] = sub[LAT_COL].astype(str) + "|" + sub[LON_COL].astype(str)

    # Prepare house number column: exclude blanks, "0", ranges, landmarks
    house = sub["מספר_בית"].astype(str).str.strip()
    exclude_mask = (
        house.isin(["", "nan", "None", "0", "NaN"])
        | sub["סוג_מיקום"].isin(["טווח בתים", "ציון דרך"])
    )
    sub["_house_for_count"] = house.where(~exclude_mask, other=np.nan)

    grouped = sub.groupby("_coord_key").agg(
        row_count=("_house_for_count", "size"),
        distinct_houses=("_house_for_count", "nunique"),
    )

    collapsed = grouped[
        (grouped["row_count"] >= COLLAPSE_MIN_ROWS)
        & (grouped["distinct_houses"] >= COLLAPSE_MIN_DISTINCT_HOUSES)
    ]

    return set(collapsed.index)


def _assign_precision(df: pd.DataFrame, collapsed_keys: set) -> pd.DataFrame:
    """Assign דיוק_גאוקוד based on method and collapsed-coordinate detection."""
    has_coords = df[LAT_COL].notna() & df[LON_COL].notna()
    df["_coord_key"] = df[LAT_COL].astype(str) + "|" + df[LON_COL].astype(str)

    tiers = pd.Series("none", index=df.index)

    for method, tier in _METHOD_TO_TIER.items():
        mask = has_coords & (df[METHOD_COL] == method)
        tiers[mask] = tier

    # Nominatim rows: check if collapsed
    nom_methods = {"nominatim_original", "nominatim", "nominatim_cached"}
    nom_mask = has_coords & df[METHOD_COL].isin(nom_methods)

    is_collapsed = df["_coord_key"].isin(collapsed_keys)
    tiers[nom_mask & is_collapsed] = "street"
    tiers[nom_mask & ~is_collapsed] = "address_unverified"

    # No coordinates → none
    tiers[~has_coords] = "none"

    df[PRECISION_COL] = tiers
    df = df.drop(columns=["_coord_key"])
    return df


def patch_v2(input_path: str, output_path: str) -> pd.DataFrame:
    """
    Full patch pipeline:
      1. Load the v2 enriched file
      2. Coerce coordinates to float64
      3. Relabel broken method values
      4. Detect collapsed coordinates and assign precision tiers
      5. Re-run enrichment (zones)
      6. Write output
    """
    df = pd.read_excel(input_path)

    # 1. Coerce coordinates
    df = _coerce_coords(df)

    # 2. Relabel broken methods
    df = _relabel_methods(df)

    # 3. Detect collapsed coords and assign precision
    collapsed_keys = _find_collapsed_coords(df)
    df = _assign_precision(df, collapsed_keys)

    # 4. Re-run enrichment
    df_enriched, _ = ep.enrich_dataframe(df)

    # Copy enrichment columns back (enrich_dataframe returns a copy)
    for col in ["רובע_פינוי", "יום_פינוי", "תלונה_ביום_פינוי"]:
        if col in df_enriched.columns:
            df[col] = df_enriched[col].values

    # 5. Write output
    df.to_excel(output_path, index=False)

    return df


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/patch_v2.py input.xlsx output.xlsx")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    print(f"Patching {input_path} → {output_path}")
    df = patch_v2(input_path, output_path)
    print(f"  Rows: {len(df):,}")
    print(f"  Precision tiers:")
    print(df[PRECISION_COL].value_counts().to_string())
    print(f"\n  Zone distribution:")
    print(df["רובע_פינוי"].value_counts().to_string())
    print(f"\n  Coordinate dtypes: lat={df[LAT_COL].dtype}, lon={df[LON_COL].dtype}")
    print("Done.")
