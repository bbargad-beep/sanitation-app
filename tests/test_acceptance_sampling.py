# -*- coding: utf-8 -*-
"""
Tests for Step 14 — Acceptance-sampling widget.

Accept criteria:
  - sample_size() follows the Poisson zero-acceptance formula
  - sample_size() caps at lot_size
  - draw_sample() returns exactly n rows without replacement
  - run_sampling_plan() returns one row per tier present
  - Zero-defect sample → "✅ קבל" verdict
  - Non-zero defect sample → "❌ דחה" verdict
  - run_sampling_plan() is reproducible with fixed seed
"""

import pandas as pd
import numpy as np
import math
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import acceptance_sampling as qs

PRECISION_COL = qs.PRECISION_COL


def _make_geocoded_df(n=50, tier="address", good=True):
    """Build a synthetic geocoded DataFrame."""
    rows = []
    for i in range(n):
        rows.append({
            "מס' פניה":    str(i + 1),
            "רחוב_ראשי":  "הבנים",
            PRECISION_COL: tier,
            "קו_רוחב":    32.165 + i * 0.0001 if good else None,
            "קו_אורך":    34.835 if good else None,
            "geocode_method": "nominatim" if good else "no_street",
        })
    return pd.DataFrame(rows)


# ── sample_size ───────────────────────────────────────────────────────────────

def test_sample_size_formula():
    """n = ceil(-ln(β) / p_reject)"""
    p, beta = 0.05, 0.10
    expected = math.ceil(-math.log(beta) / p)
    assert qs.sample_size(1000, p, beta) == expected


def test_sample_size_capped_at_lot_size():
    small_lot = 5
    assert qs.sample_size(small_lot, 0.01, 0.10) == small_lot


def test_sample_size_zero_lot():
    assert qs.sample_size(0, 0.05) == 0


def test_sample_size_invalid_p_reject():
    with pytest.raises(ValueError):
        qs.sample_size(100, 0.0)


def test_sample_size_invalid_beta():
    with pytest.raises(ValueError):
        qs.sample_size(100, 0.05, beta=0.0)


# ── draw_sample ───────────────────────────────────────────────────────────────

def test_draw_sample_correct_size():
    df = _make_geocoded_df(100)
    sample = qs.draw_sample(df, 20, seed=42)
    assert len(sample) == 20


def test_draw_sample_no_replacement():
    df = _make_geocoded_df(100)
    sample = qs.draw_sample(df, 50, seed=7)
    assert len(sample) == len(sample.index.unique())


def test_draw_sample_capped_at_df_size():
    df = _make_geocoded_df(10)
    sample = qs.draw_sample(df, 999, seed=1)
    assert len(sample) == 10


def test_draw_sample_empty_df():
    df = _make_geocoded_df(0)
    sample = qs.draw_sample(df, 5)
    assert len(sample) == 0


# ── run_sampling_plan ─────────────────────────────────────────────────────────

def test_run_sampling_plan_returns_dataframe():
    df = _make_geocoded_df(100, tier="address", good=True)
    result = qs.run_sampling_plan(df, seed=42)
    assert isinstance(result, pd.DataFrame)


def test_run_sampling_plan_required_columns():
    df = _make_geocoded_df(100, tier="address", good=True)
    result = qs.run_sampling_plan(df, seed=42)
    for col in ("רמת_גאוקוד", "גודל_מנה", "גודל_דגימה", "פגמים", "פסיקה"):
        assert col in result.columns, f"Missing column: {col}"


def test_run_sampling_plan_one_row_per_tier():
    """With two tiers, plan produces two rows."""
    df1 = _make_geocoded_df(50, tier="address")
    df2 = _make_geocoded_df(50, tier="street")
    df = pd.concat([df1, df2], ignore_index=True)
    result = qs.run_sampling_plan(df, seed=42)
    assert len(result) == 2
    assert set(result["רמת_גאוקוד"]) == {"address", "street"}


def test_zero_defect_sample_gives_accept():
    """All good rows → 0 defects → ✅ קבל."""
    df = _make_geocoded_df(200, tier="address", good=True)
    result = qs.run_sampling_plan(df, seed=42)
    row = result[result["רמת_גאוקוד"] == "address"].iloc[0]
    assert row["פגמים"] == 0
    assert "✅" in row["פסיקה"]


def test_all_defective_sample_gives_reject():
    """All bad rows → ≥1 defect → ❌ דחה."""
    df = _make_geocoded_df(200, tier="address", good=False)
    result = qs.run_sampling_plan(df, seed=42)
    row = result[result["רמת_גאוקוד"] == "address"].iloc[0]
    assert row["פגמים"] >= 1
    assert "❌" in row["פסיקה"]


def test_reproducible_with_seed():
    """Same seed → same result."""
    df = _make_geocoded_df(500, tier="street", good=True)
    r1 = qs.run_sampling_plan(df, seed=99)
    r2 = qs.run_sampling_plan(df, seed=99)
    pd.testing.assert_frame_equal(r1, r2)


def test_custom_defect_fn():
    """Custom defect_fn is respected."""
    df = _make_geocoded_df(100, tier="address", good=True)
    # Flag all rows as defective
    result = qs.run_sampling_plan(df, defect_fn=lambda row, tier: True, seed=1)
    row = result.iloc[0]
    assert row["פגמים"] == row["גודל_דגימה"]
    assert "❌" in row["פסיקה"]


def test_no_precision_col_falls_back():
    """DataFrame without PRECISION_COL runs on the whole lot as one group."""
    df = _make_geocoded_df(100, tier="address", good=True)
    df = df.drop(columns=[PRECISION_COL])
    result = qs.run_sampling_plan(df, seed=42)
    assert len(result) == 1
