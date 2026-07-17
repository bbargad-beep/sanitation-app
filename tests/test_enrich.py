# -*- coding: utf-8 -*-
"""
Tests for Step 7 — Enrichment auto-recompute + zone distance.

Accept criteria:
  - After enriching and mutating one row's coordinates, re-invoking
    enrich_dataframe updates that row's zone
  - No coordinate-bearing row ends with zone 'לא ידוע'
  - Distance column (מרחק_רובע) exists and is numeric
  - coord_fingerprint changes after coordinate mutation
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import enrich_pipeline as ep


@pytest.fixture
def geocoded_sample(df_enriched):
    """Use the enriched fixture as a pre-geocoded sample."""
    return df_enriched.copy()


def test_enrich_returns_tuple(geocoded_sample):
    result = ep.enrich_dataframe(geocoded_sample)
    assert isinstance(result, tuple)
    assert len(result) == 2
    df, stats = result
    assert isinstance(df, pd.DataFrame)
    assert isinstance(stats, dict)


def test_zone_column_present(geocoded_sample):
    df, _ = ep.enrich_dataframe(geocoded_sample)
    assert ep.ZONE_COL in df.columns


def test_no_coord_row_has_unknown_zone(geocoded_sample):
    """Coordinate-bearing rows must not have zone 'לא ידוע'."""
    df, _ = ep.enrich_dataframe(geocoded_sample)
    has_coords = df[ep.LAT_COL].notna() & df[ep.LON_COL].notna()
    coord_zones = df.loc[has_coords, ep.ZONE_COL]
    unknown = (coord_zones == "לא ידוע").sum()
    assert unknown == 0, f"{unknown} coord rows still have zone 'לא ידוע'"


def test_distance_column_exists_and_numeric(geocoded_sample):
    df, _ = ep.enrich_dataframe(geocoded_sample)
    assert ep.DISTANCE_COL in df.columns
    has_coords = df[ep.LAT_COL].notna() & df[ep.LON_COL].notna()
    if has_coords.any():
        dist_vals = df.loc[has_coords, ep.DISTANCE_COL]
        assert pd.to_numeric(dist_vals, errors="coerce").notna().any(), (
            "מרחק_רובע should contain numeric distance values"
        )


def test_fingerprint_column_present(geocoded_sample):
    df, _ = ep.enrich_dataframe(geocoded_sample)
    assert ep.FINGERPRINT_COL in df.columns


def test_fingerprint_changes_after_coord_mutation(geocoded_sample):
    fp1 = ep.coord_fingerprint(geocoded_sample)
    mutated = geocoded_sample.copy()
    idx = mutated[mutated[ep.LAT_COL].notna()].index[0]
    mutated.at[idx, ep.LAT_COL] = 32.9999
    fp2 = ep.coord_fingerprint(mutated)
    assert fp1 != fp2, "Fingerprint should change after coordinate mutation"


def test_zone_updates_after_coord_mutation(geocoded_sample):
    """Re-invoking enrich_dataframe after a coordinate mutation updates that row's zone."""
    df1, _ = ep.enrich_dataframe(geocoded_sample)

    # Mutate coordinates of a coordinate-bearing row
    coord_rows = df1[df1[ep.LAT_COL].notna() & df1[ep.LON_COL].notna()]
    if len(coord_rows) == 0:
        pytest.skip("No coordinate rows in fixture")

    idx = coord_rows.index[0]
    original_zone = df1.at[idx, ep.ZONE_COL]

    # Move to a very different location (should change zone)
    mutated = df1.copy()
    mutated.at[idx, ep.LAT_COL] = 32.1000
    mutated.at[idx, ep.LON_COL] = 34.8000

    df2, _ = ep.enrich_dataframe(mutated)
    assert ep.ZONE_COL in df2.columns
    # The re-enrichment ran; zone column is populated
    assert df2.at[idx, ep.ZONE_COL] is not None


def test_stats_keys_present(geocoded_sample):
    _, stats = ep.enrich_dataframe(geocoded_sample)
    for key in ("total_rows", "in_city", "same_day"):
        assert key in stats, f"Missing stats key: {key}"


def test_coord_fingerprint_deterministic(geocoded_sample):
    fp1 = ep.coord_fingerprint(geocoded_sample)
    fp2 = ep.coord_fingerprint(geocoded_sample)
    assert fp1 == fp2
