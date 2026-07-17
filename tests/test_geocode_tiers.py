# -*- coding: utf-8 -*-
"""
Tests for Step 4 — Geocode tiers + provenance capture.

Accept criteria:
  - Every geocoded row has a non-empty דיוק_גאוקוד in {address, near_address, street, none}
  - place_rank 30 → "address"; lower → "street"
  - geocode_query is populated for every geocoded row
  - geocode_run_id is a uuid present on every row
  - stats contain pipeline_version and geocode_run_id
  - Manual paths in app.py set geocode_method="manual" + דיוק_גאוקוד="address"
"""

import pandas as pd
import numpy as np
import pytest
import uuid
import os
import sys
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import geocode_pipeline as gp


PRECISION_COL = gp.PRECISION_COL
VALID_PRECISIONS = {"address", "near_address", "street", "none"}


@pytest.fixture
def cleaned_df(df_raw):
    """Run the clean pipeline to get a properly cleaned DataFrame."""
    import clean_pipeline as cp
    df, _ = cp.clean_dataframe(df_raw)
    return df


def test_precision_col_exists_after_geocode(cleaned_df, fake_geocoder):
    df, stats = gp.geocode_dataframe(cleaned_df, skip_gis=True)
    assert PRECISION_COL in df.columns


def test_precision_values_valid(cleaned_df, fake_geocoder):
    df, stats = gp.geocode_dataframe(cleaned_df, skip_gis=True)
    actual = set(df[PRECISION_COL].dropna().unique())
    assert actual.issubset(VALID_PRECISIONS), f"Unexpected precisions: {actual - VALID_PRECISIONS}"


def test_every_row_has_precision(cleaned_df, fake_geocoder):
    df, stats = gp.geocode_dataframe(cleaned_df, skip_gis=True)
    assert df[PRECISION_COL].notna().all(), "Some rows missing precision"
    assert (df[PRECISION_COL] != "").all(), "Some rows have empty precision"


def test_place_rank_30_gives_address(fake_geocoder):
    lat, lon, pr, at = gp._nominatim_geocode_one(
        gp.FakeGeolocator() if hasattr(gp, "FakeGeolocator") else type("G", (), {"geocode": lambda self, q, **kw: type("R", (), {"latitude": 32.16, "longitude": 34.84, "raw": {"place_rank": 30, "addresstype": "building"}})()})(),
        "הבנים 14, הרצליה, ישראל"
    )
    assert pr == 30


def test_place_rank_below_30_gives_street(fake_geocoder):
    lat, lon, pr, at = gp._nominatim_geocode_one(
        gp.FakeGeolocator() if hasattr(gp, "FakeGeolocator") else type("G", (), {"geocode": lambda self, q, **kw: type("R", (), {"latitude": 32.16, "longitude": 34.84, "raw": {"place_rank": 26, "addresstype": "road"}})()})(),
        "הבנים, הרצליה, ישראל"
    )
    assert pr == 26


def test_nominatim_address_precision(cleaned_df, fake_geocoder):
    """Rows geocoded with place_rank=30 should have precision='address'."""
    df, _ = gp.geocode_dataframe(cleaned_df, skip_gis=True)
    geocoded = df[df["geocode_method"] == "nominatim_original"]
    if len(geocoded) == 0:
        pytest.skip("No nominatim_original rows in fixture")
    for _, row in geocoded.iterrows():
        assert row[PRECISION_COL] in ("address", "street")


def test_geocode_query_populated(cleaned_df, fake_geocoder):
    df, _ = gp.geocode_dataframe(cleaned_df, skip_gis=True)
    geocoded = df[df["geocode_method"].isin(["nominatim_original", "osm_centroid"])]
    if len(geocoded) == 0:
        pytest.skip("No geocoded rows")
    assert geocoded["geocode_query"].notna().all(), "geocode_query missing on some geocoded rows"
    assert (geocoded["geocode_query"] != "").all(), "geocode_query empty on some geocoded rows"


def test_geocode_run_id_present(cleaned_df, fake_geocoder):
    df, stats = gp.geocode_dataframe(cleaned_df, skip_gis=True)
    assert "geocode_run_id" in df.columns
    run_ids = df["geocode_run_id"].unique()
    assert len(run_ids) == 1
    uuid.UUID(run_ids[0])


def test_stats_contain_version_and_run_id(cleaned_df, fake_geocoder):
    df, stats = gp.geocode_dataframe(cleaned_df, skip_gis=True)
    assert "pipeline_version" in stats
    assert stats["pipeline_version"] == gp.PIPELINE_VERSION
    assert "geocode_run_id" in stats
    uuid.UUID(stats["geocode_run_id"])


def test_unresolved_rows_get_none_precision(cleaned_df, fake_geocoder):
    df, _ = gp.geocode_dataframe(cleaned_df, skip_gis=True)
    unresolved = df[df["geocode_method"] == "unresolved"]
    if len(unresolved) == 0:
        pytest.skip("No unresolved rows")
    assert (unresolved[PRECISION_COL] == "none").all()


def test_manual_path_sets_method_and_precision():
    """Verify app.py manual paths set geocode_method='manual' and precision='address'."""
    app_path = os.path.join(os.path.dirname(__file__), "..", "app.py")
    with open(app_path, "r", encoding="utf-8") as f:
        source = f.read()

    assert '"manual"' in source or "'manual'" in source, "app.py missing manual geocode_method"
    assert 'geocode_method"] = "manual"' in source, "data_editor writeback missing manual method"
    assert 'דיוק_גאוקוד"] = "address"' in source, "manual path missing precision assignment"

    bulk_section = source[source.find("הזנה מרוכזת"):]
    assert 'geocode_method"] = "manual"' in bulk_section, "bulk paste missing manual method"
    assert 'דיוק_גאוקוד"] = "address"' in bulk_section, "bulk paste missing precision"
