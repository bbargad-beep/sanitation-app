# -*- coding: utf-8 -*-
"""
Tests for Step 12 — Tiered triage UI + map-pin picker.

Accept criteria:
  - build_triage_groups() partitions flagged df into blocking/review/info/clean
  - Each group is a non-overlapping subset of the original rows
  - triage_summary() returns correct counts
  - _leaflet_map_html() produces HTML containing Leaflet script tag and markers
"""

import pandas as pd
import numpy as np
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import flags as fl
import app as _app


def _make_mixed_df():
    """DataFrame with rows of different severity after detect_flags."""
    rows = [
        # blocking: blank street with כתובת type
        {"מס' פניה": "1", "תאריך": "2024-06-15", "רחוב_ראשי": None,
         "מספר_בית": "", "סוג_מיקום": "כתובת", "קו_רוחב": None, "קו_אורך": None,
         "geocode_method": "", "תת_נושא_חדש": "אי פינוי", "סטטוס פנייה": "סגור"},
        # warn: missing house number
        {"מס' פניה": "2", "תאריך": "2024-06-15", "רחוב_ראשי": "הבנים",
         "מספר_בית": None, "סוג_מיקום": "כתובת", "קו_רוחב": 32.165, "קו_אורך": 34.835,
         "geocode_method": "nominatim", "תת_נושא_חדש": "אי פינוי", "סטטוס פנייה": "סגור"},
        # clean
        {"מס' פניה": "3", "תאריך": "2024-06-15", "רחוב_ראשי": "סוקולוב",
         "מספר_בית": "5", "סוג_מיקום": "כתובת", "קו_רוחב": 32.165, "קו_אורך": 34.835,
         "geocode_method": "nominatim", "תת_נושא_חדש": "אי פינוי", "סטטוס פנייה": "סגור"},
    ]
    df = pd.DataFrame(rows)
    return fl.detect_flags(df, stage="clean")


# ── build_triage_groups ───────────────────────────────────────────────────────

def test_triage_groups_keys():
    flagged = _make_mixed_df()
    groups = fl.build_triage_groups(flagged)
    assert set(groups.keys()) == {"blocking", "review", "info", "clean"}


def test_triage_groups_are_dataframes():
    flagged = _make_mixed_df()
    groups = fl.build_triage_groups(flagged)
    for name, grp in groups.items():
        assert isinstance(grp, pd.DataFrame), f"Group {name!r} is not a DataFrame"


def test_triage_groups_non_overlapping():
    """Row indices must be disjoint across all groups."""
    flagged = _make_mixed_df()
    groups = fl.build_triage_groups(flagged)
    all_idx = []
    for grp in groups.values():
        all_idx.extend(grp.index.tolist())
    assert len(all_idx) == len(set(all_idx)), "Groups contain overlapping row indices"


def test_triage_groups_cover_all_rows():
    """Union of all groups must equal the full flagged DataFrame."""
    flagged = _make_mixed_df()
    groups = fl.build_triage_groups(flagged)
    total = sum(len(g) for g in groups.values())
    assert total == len(flagged), f"Groups cover {total} rows but flagged has {len(flagged)}"


def test_triage_blocking_group_correct():
    flagged = _make_mixed_df()
    groups = fl.build_triage_groups(flagged)
    assert len(groups["blocking"]) >= 1
    assert all(groups["blocking"]["_flag_severity"] == "block")


def test_triage_review_group_correct():
    flagged = _make_mixed_df()
    groups = fl.build_triage_groups(flagged)
    assert len(groups["review"]) >= 1
    assert all(groups["review"]["_flag_severity"].isin(["warn", "review"]))


def test_triage_clean_group_has_no_flags():
    flagged = _make_mixed_df()
    groups = fl.build_triage_groups(flagged)
    assert all(groups["clean"]["_flag_severity"] == "")


def test_triage_groups_without_flag_col():
    """build_triage_groups on a df without _flag_severity returns all rows in clean."""
    df = pd.DataFrame([{"מס' פניה": "1", "רחוב_ראשי": "הבנים"}])
    groups = fl.build_triage_groups(df)
    assert len(groups["clean"]) == 1
    assert len(groups["blocking"]) == 0


# ── triage_summary ────────────────────────────────────────────────────────────

def test_triage_summary_returns_dict():
    flagged = _make_mixed_df()
    groups = fl.build_triage_groups(flagged)
    summary = fl.triage_summary(groups)
    assert isinstance(summary, dict)


def test_triage_summary_sums_to_total():
    flagged = _make_mixed_df()
    groups = fl.build_triage_groups(flagged)
    summary = fl.triage_summary(groups)
    assert sum(summary.values()) == len(flagged)


# ── _leaflet_map_html ─────────────────────────────────────────────────────────

def test_leaflet_map_html_returns_string():
    flagged = _make_mixed_df()
    html = _app._leaflet_map_html(flagged)
    assert isinstance(html, str)


def test_leaflet_map_html_contains_leaflet_script():
    flagged = _make_mixed_df()
    html = _app._leaflet_map_html(flagged)
    assert "leaflet" in html.lower(), "Leaflet script not found in map HTML"


def test_leaflet_map_html_contains_coords():
    """HTML should contain at least one geocoded coordinate from the data."""
    flagged = _make_mixed_df()
    html = _app._leaflet_map_html(flagged)
    # Row 2 and 3 have lat=32.165, lon=34.835
    assert "32.165" in html


def test_leaflet_map_html_skips_null_coords():
    """Rows without coordinates must not appear as points."""
    flagged = _make_mixed_df()
    html = _app._leaflet_map_html(flagged)
    # Ticket "1" has no coords; its street name "None" should not add a marker
    # The JSON points list should only have 2 entries (rows 2 and 3)
    import json, re
    m = re.search(r'var pts = (\[.*?\]);', html, re.DOTALL)
    if m:
        pts = json.loads(m.group(1))
        assert len(pts) == 2, f"Expected 2 map points, got {len(pts)}"
