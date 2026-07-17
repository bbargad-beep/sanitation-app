# -*- coding: utf-8 -*-
"""
Tests for scripts/patch_v2.py — precision backfill and provenance repair.

Accept criteria (Step 2):
  - No coordinate-bearing row has zone "לא ידוע"
  - No coordinate-bearing row has method "unresolved"
  - Both coord columns are float64
  - Every row has a non-empty דיוק_גאוקוד
"""

import pandas as pd
import numpy as np
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from patch_v2 import (
    _coerce_coords,
    _relabel_methods,
    _find_collapsed_coords,
    _assign_precision,
    patch_v2,
    PRECISION_COL,
    LAT_COL,
    LON_COL,
    METHOD_COL,
)


def test_coerce_strips_trailing_comma():
    df = pd.DataFrame({
        LAT_COL: ["32.16110360743059,", "32.170"],
        LON_COL: ["34.84530,", "34.845"],
    })
    result = _coerce_coords(df)
    assert result[LAT_COL].dtype == np.float64
    assert result[LON_COL].dtype == np.float64
    assert abs(result[LAT_COL].iloc[0] - 32.16110360743059) < 1e-8


def test_relabel_unresolved_with_coords():
    df = pd.DataFrame({
        LAT_COL: [32.16, None, 32.17],
        LON_COL: [34.84, None, 34.85],
        METHOD_COL: ["unresolved", "unresolved", "flagged_description"],
    })
    result = _relabel_methods(df)
    assert result.loc[0, METHOD_COL] == "manual_backfilled"
    assert result.loc[1, METHOD_COL] == "unresolved"  # no coords → stays
    assert result.loc[2, METHOD_COL] == "manual_backfilled"


def test_relabel_no_street_with_coords():
    df = pd.DataFrame({
        LAT_COL: [32.16],
        LON_COL: [34.84],
        METHOD_COL: ["no_street"],
    })
    result = _relabel_methods(df)
    assert result.loc[0, METHOD_COL] == "manual_backfilled"


def test_find_collapsed_coords():
    """5 rows sharing one coordinate with 4 distinct house numbers → collapsed."""
    df = pd.DataFrame({
        LAT_COL: [32.16] * 6,
        LON_COL: [34.84] * 6,
        "מספר_בית": ["1", "2", "3", "4", "5", "1"],
        "סוג_מיקום": ["כתובת"] * 6,
    })
    keys = _find_collapsed_coords(df)
    assert len(keys) == 1


def test_collapsed_excludes_nan_and_zero():
    """NaN and '0' house numbers don't count toward distinct houses."""
    df = pd.DataFrame({
        LAT_COL: [32.16] * 6,
        LON_COL: [34.84] * 6,
        "מספר_בית": ["1", "2", "0", np.nan, "0", "1"],
        "סוג_מיקום": ["כתובת"] * 6,
    })
    keys = _find_collapsed_coords(df)
    assert len(keys) == 0  # only 2 distinct valid houses


def test_collapsed_excludes_range_type():
    df = pd.DataFrame({
        LAT_COL: [32.16] * 6,
        LON_COL: [34.84] * 6,
        "מספר_בית": ["1", "2", "3", "4", "5", "6"],
        "סוג_מיקום": ["כתובת", "כתובת", "כתובת", "טווח בתים", "ציון דרך", "כתובת"],
    })
    keys = _find_collapsed_coords(df)
    # Houses 4 and 5 are excluded → only 1,2,3,6 = 4 distinct → passes threshold
    assert len(keys) == 1


def test_assign_precision_nominatim_collapsed():
    df = pd.DataFrame({
        LAT_COL: [32.16] * 5 + [32.17],
        LON_COL: [34.84] * 5 + [34.85],
        METHOD_COL: ["nominatim_original"] * 5 + ["nominatim_original"],
        "מספר_בית": ["1", "2", "3", "4", "5", "10"],
        "סוג_מיקום": ["כתובת"] * 6,
    })
    collapsed = _find_collapsed_coords(df)
    result = _assign_precision(df, collapsed)
    # First 5 share a collapsed point → street
    assert all(result.loc[:4, PRECISION_COL] == "street")
    # Row 5 is alone → address_unverified
    assert result.loc[5, PRECISION_COL] == "address_unverified"


def test_assign_precision_gis_methods():
    df = pd.DataFrame({
        LAT_COL: [32.16, 32.17, 32.18],
        LON_COL: [34.84, 34.85, 34.86],
        METHOD_COL: ["gis_exact", "gis_nearest", "gis_centroid"],
        "מספר_בית": ["1", "2", "3"],
        "סוג_מיקום": ["כתובת"] * 3,
    })
    result = _assign_precision(df, set())
    assert result.loc[0, PRECISION_COL] == "address"
    assert result.loc[1, PRECISION_COL] == "near_address"
    assert result.loc[2, PRECISION_COL] == "street"


def test_assign_precision_no_coords():
    df = pd.DataFrame({
        LAT_COL: [None],
        LON_COL: [None],
        METHOD_COL: ["unresolved"],
        "מספר_בית": [""],
        "סוג_מיקום": [""],
    })
    result = _assign_precision(df, set())
    assert result.loc[0, PRECISION_COL] == "none"


def test_patch_v2_on_enriched_fixture(df_enriched, tmp_xlsx):
    """Full integration test on the 100-row enriched fixture."""
    input_path = tmp_xlsx(df_enriched, "enriched_input.xlsx")
    output_path = input_path.replace("enriched_input", "patched_output")

    result = patch_v2(input_path, output_path)

    has_coords = result[LAT_COL].notna() & result[LON_COL].notna()

    # No coordinate-bearing row has zone "לא ידוע"
    coord_zones = result.loc[has_coords, "רובע_פינוי"]
    assert (coord_zones != "לא ידוע").all(), (
        f"Found {(coord_zones == 'לא ידוע').sum()} coord rows with zone 'לא ידוע'"
    )

    # No coordinate-bearing row has method "unresolved"
    coord_methods = result.loc[has_coords, METHOD_COL]
    assert (coord_methods != "unresolved").all(), (
        f"Found {(coord_methods == 'unresolved').sum()} coord rows with method 'unresolved'"
    )

    # Both coord columns are float64
    assert result[LAT_COL].dtype == np.float64, f"lat dtype: {result[LAT_COL].dtype}"
    assert result[LON_COL].dtype == np.float64, f"lon dtype: {result[LON_COL].dtype}"

    # Every row has a non-empty דיוק_גאוקוד
    assert PRECISION_COL in result.columns
    assert result[PRECISION_COL].notna().all()
    assert (result[PRECISION_COL] != "").all()

    # Output file was written
    assert os.path.exists(output_path)
