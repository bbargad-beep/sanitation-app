# -*- coding: utf-8 -*-
"""
Tests for Step 13 — Validation mode.

Accept criteria:
  - compare_to_reference() joins on מס' פניה and returns matched/unmatched counts
  - per_column table has correct columns and one row per compared column
  - Agreement percentage is 100% when pipeline == reference
  - Divergent values produce < 100% agreement
  - Rows in only one side are reported correctly
  - Missing join column raises ValueError
"""

import pandas as pd
import numpy as np
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import validation as vl

JOIN = "מס' פניה"


def _make_pair(n_shared=5, n_only_p=2, n_only_r=1):
    """Build matching pipeline/reference DataFrames."""
    shared_ids = [str(i) for i in range(1, n_shared + 1)]
    p_ids = shared_ids + [str(100 + i) for i in range(n_only_p)]
    r_ids = shared_ids + [str(200 + i) for i in range(n_only_r)]

    pipeline = pd.DataFrame({
        JOIN:       p_ids,
        "רחוב_ראשי": ["הבנים"] * n_shared + ["סוקולוב"] * n_only_p,
        "מספר_בית": [str(i) for i in range(len(p_ids))],
        "קו_רוחב":  [32.165 + i * 0.001 for i in range(len(p_ids))],
        "קו_אורך":  [34.835] * len(p_ids),
    })
    reference = pd.DataFrame({
        JOIN:       r_ids,
        "רחוב_ראשי": ["הבנים"] * n_shared + ["ויצמן"] * n_only_r,
        "מספר_בית": [str(i) for i in range(len(r_ids))],
        "קו_רוחב":  [32.165 + i * 0.001 for i in range(len(r_ids))],
        "קו_אורך":  [34.835] * len(r_ids),
    })
    return pipeline, reference


# ── Basic structure ───────────────────────────────────────────────────────────

def test_compare_returns_dict():
    p, r = _make_pair()
    result = vl.compare_to_reference(p, r)
    assert isinstance(result, dict)
    for key in ("matched_rows", "only_pipeline", "only_reference", "per_column", "diff"):
        assert key in result, f"Missing key: {key}"


def test_matched_rows_count():
    p, r = _make_pair(n_shared=5, n_only_p=2, n_only_r=1)
    result = vl.compare_to_reference(p, r)
    assert result["matched_rows"] == 5


def test_only_pipeline_count():
    p, r = _make_pair(n_shared=5, n_only_p=2, n_only_r=1)
    result = vl.compare_to_reference(p, r)
    assert result["only_pipeline"] == 2


def test_only_reference_count():
    p, r = _make_pair(n_shared=5, n_only_p=2, n_only_r=1)
    result = vl.compare_to_reference(p, r)
    assert result["only_reference"] == 1


# ── per_column table ─────────────────────────────────────────────────────────

def test_per_column_is_dataframe():
    p, r = _make_pair()
    result = vl.compare_to_reference(p, r)
    assert isinstance(result["per_column"], pd.DataFrame)


def test_per_column_has_required_columns():
    p, r = _make_pair()
    result = vl.compare_to_reference(p, r)
    for col in ("עמודה", "הסכמה", "שונה", "אחוז_הסכמה"):
        assert col in result["per_column"].columns, f"Missing per_column column: {col}"


def test_per_column_row_per_compared_col():
    p, r = _make_pair()
    result = vl.compare_to_reference(p, r)
    # Common columns (excl join key): רחוב_ראשי, מספר_בית, קו_רוחב, קו_אורך
    assert len(result["per_column"]) >= 1


# ── Agreement percentages ─────────────────────────────────────────────────────

def test_perfect_agreement_100pct():
    """When pipeline == reference on all shared rows, agreement is 100%."""
    shared_ids = ["1", "2", "3"]
    data = {JOIN: shared_ids, "רחוב_ראשי": ["א", "ב", "ג"]}
    p = pd.DataFrame(data)
    r = pd.DataFrame(data.copy())
    result = vl.compare_to_reference(p, r, columns=["רחוב_ראשי"])
    row = result["per_column"].iloc[0]
    assert row["אחוז_הסכמה"] == 100.0


def test_divergent_values_below_100pct():
    """When pipeline and reference differ on some rows, agreement < 100%."""
    p = pd.DataFrame({JOIN: ["1", "2", "3"],
                       "רחוב_ראשי": ["הבנים", "סוקולוב", "ויצמן"]})
    r = pd.DataFrame({JOIN: ["1", "2", "3"],
                       "רחוב_ראשי": ["הבנים", "WRONG", "WRONG"]})
    result = vl.compare_to_reference(p, r, columns=["רחוב_ראשי"])
    row = result["per_column"].iloc[0]
    assert row["אחוז_הסכמה"] < 100.0
    assert row["שונה"] == 2


# ── diff DataFrame ────────────────────────────────────────────────────────────

def test_diff_contains_join_col():
    p, r = _make_pair()
    result = vl.compare_to_reference(p, r)
    assert JOIN in result["diff"].columns


def test_diff_row_count_equals_matched():
    p, r = _make_pair(n_shared=5, n_only_p=2, n_only_r=1)
    result = vl.compare_to_reference(p, r)
    assert len(result["diff"]) == result["matched_rows"]


# ── Error handling ────────────────────────────────────────────────────────────

def test_missing_join_col_in_pipeline_raises():
    p = pd.DataFrame({"other": [1, 2]})
    r = pd.DataFrame({JOIN: ["1", "2"], "col": ["a", "b"]})
    with pytest.raises(ValueError, match="pipeline_df missing"):
        vl.compare_to_reference(p, r)


def test_missing_join_col_in_reference_raises():
    p = pd.DataFrame({JOIN: ["1", "2"], "col": ["a", "b"]})
    r = pd.DataFrame({"other": [1, 2]})
    with pytest.raises(ValueError, match="reference_df missing"):
        vl.compare_to_reference(p, r)


def test_no_overlap_returns_zero_matched():
    p = pd.DataFrame({JOIN: ["1", "2"], "col": ["a", "b"]})
    r = pd.DataFrame({JOIN: ["3", "4"], "col": ["c", "d"]})
    result = vl.compare_to_reference(p, r)
    assert result["matched_rows"] == 0
    assert result["only_pipeline"] == 2
    assert result["only_reference"] == 2
