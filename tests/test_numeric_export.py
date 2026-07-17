# -*- coding: utf-8 -*-
"""
Tests for Step 10 — Numeric export guarantee.

Accept criteria:
  - excel_bytes output has קו_רוחב / קו_אורך as float64 in the נתונים sheet
  - Stringified coords ("32.16,") and None values are handled without error
  - _coerce_coords is idempotent (second call is a no-op)
"""

import io
import pandas as pd
import numpy as np
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as _app


def _minimal_df(n=5, coord_format="float"):
    """Build a minimal DataFrame for export testing."""
    rows = []
    for i in range(n):
        lat = 32.16 + i * 0.001
        lon = 34.83 + i * 0.001
        if coord_format == "string_comma":
            lat = f"{lat},"
            lon = f"{lon},"
        elif coord_format == "none":
            lat = None
            lon = None
        rows.append({
            "מס' פניה":      str(i + 1),
            "תאריך":         "2024-06-15",
            "רחוב_ראשי":     "הבנים",
            "מספר_בית":      str(i + 1),
            "סוג_מיקום":     "כתובת",
            "קו_רוחב":       lat,
            "קו_אורך":       lon,
            "geocode_method": "nominatim",
            "תת_נושא_חדש":   "אי פינוי",
        })
    return pd.DataFrame(rows)


def _read_coord_col(xlsx_bytes: bytes, col_name: str) -> pd.Series:
    buf = io.BytesIO(xlsx_bytes)
    df = pd.read_excel(buf, sheet_name="נתונים")
    assert col_name in df.columns, f"{col_name} not found in נתונים sheet"
    return df[col_name]


def test_coord_cols_are_numeric_in_export():
    """excel_bytes must write coords as numbers, not strings."""
    df = _minimal_df(coord_format="float")
    stats = {}
    xb = _app.excel_bytes(df, stats)
    lat_col = _read_coord_col(xb, "קו_רוחב")
    lon_col = _read_coord_col(xb, "קו_אורך")
    assert pd.to_numeric(lat_col, errors="coerce").notna().all(), \
        "קו_רוחב contains non-numeric values in export"
    assert pd.to_numeric(lon_col, errors="coerce").notna().all(), \
        "קו_אורך contains non-numeric values in export"


def test_stringified_coords_coerced():
    """String coords with trailing commas are coerced to float in export."""
    df = _minimal_df(coord_format="string_comma")
    stats = {}
    xb = _app.excel_bytes(df, stats)
    lat_col = _read_coord_col(xb, "קו_רוחב")
    assert pd.to_numeric(lat_col, errors="coerce").notna().all(), \
        "Stringified coords not coerced in export"


def test_none_coords_become_nan():
    """None coordinate values become NaN (blank) in export — not strings."""
    df = _minimal_df(coord_format="none")
    stats = {}
    xb = _app.excel_bytes(df, stats)
    lat_col = _read_coord_col(xb, "קו_רוחב")
    # All should be NaN — no string "None" values
    non_nan = lat_col.dropna()
    for v in non_nan:
        assert not isinstance(v, str), f"Expected NaN, got string: {v!r}"


def test_coerce_coords_idempotent():
    """_coerce_coords called twice yields the same result as once."""
    df = _minimal_df(coord_format="float")
    once  = _app._coerce_coords(df)
    twice = _app._coerce_coords(once)
    pd.testing.assert_frame_equal(once[["קו_רוחב", "קו_אורך"]],
                                   twice[["קו_רוחב", "קו_אורך"]])


def test_coord_dtype_float64():
    """_coerce_coords guarantees float64 dtype on both coord columns."""
    df = _minimal_df(coord_format="string_comma")
    result = _app._coerce_coords(df)
    assert result["קו_רוחב"].dtype == np.float64, "קו_רוחב dtype should be float64"
    assert result["קו_אורך"].dtype == np.float64, "קו_אורך dtype should be float64"
