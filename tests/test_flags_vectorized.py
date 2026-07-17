# -*- coding: utf-8 -*-
"""
Tests for Step 9 — Vectorized flags + cache.

Accept criteria:
  - detect_flags output is identical to the reference (iterrows) implementation
    on the enriched fixture at all three stages
  - detect_flags on a 17k-row synthetic frame completes in < 1.0 s
  - flags_cache_key is deterministic and changes when data changes
"""

import time
import pandas as pd
import numpy as np
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import flags as fl


# ── Reference (iterrows) implementation ──────────────────────────────────────

def _is_blank_ref(v) -> bool:
    if pd.isna(v):
        return True
    s = str(v).strip()
    return s == "" or s.lower() in ("nan", "none")


import re as _re

def _only_punct_or_num_ref(v) -> bool:
    if _is_blank_ref(v):
        return False
    s = str(v).strip()
    return bool(_re.fullmatch(r"[\d\s\.\,\-\_\!\?\(\)״׳'\"]+", s))


def detect_flags_ref(df: pd.DataFrame,
                     date_min: str = None, date_max: str = None,
                     stage: str = "clean") -> pd.DataFrame:
    """Reference iterrows implementation kept for golden comparison."""
    HERZLIYA_BOUNDS = fl.HERZLIYA_BOUNDS
    SEA_LON_MAX = fl.SEA_LON_MAX
    KNOWN_CATEGORIES = fl.KNOWN_CATEGORIES
    DESCRIPTIVE_LOC_TYPES = fl.DESCRIPTIVE_LOC_TYPES

    df = df.copy()
    flags_per_row = [[] for _ in range(len(df))]

    if "תאריך" in df.columns and (date_min or date_max):
        dates = pd.to_datetime(df["תאריך"], errors="coerce")
        for pos, d in enumerate(dates):
            if pd.notna(d):
                if date_min and d < pd.to_datetime(date_min):
                    flags_per_row[pos].append(("date_early", "תאריך לפני התקופה", "warn"))
                if date_max and d > pd.to_datetime(date_max):
                    flags_per_row[pos].append(("date_late", "תאריך אחרי התקופה", "warn"))

    for pos, (_, row) in enumerate(df.iterrows()):
        _lat = pd.to_numeric(str(row.get("קו_רוחב", "")).replace(",", ""), errors="coerce")
        _lon = pd.to_numeric(str(row.get("קו_אורך", "")).replace(",", ""), errors="coerce")
        has_coords = pd.notna(_lat) and pd.notna(_lon)
        addr_sev = "warn" if (stage in ("geocode", "all") and has_coords) else "block"

        if "תאריך" in df.columns and _is_blank_ref(row.get("תאריך")):
            flags_per_row[pos].append(("no_date", "חסר תאריך", "block"))
        if "מס' פניה" in df.columns and _is_blank_ref(row.get("מס' פניה")):
            flags_per_row[pos].append(("no_id", "חסר מספר פניה", "block"))

        loc_type = str(row.get("סוג_מיקום", "")).strip()
        street = row.get("רחוב_ראשי", "")

        if _is_blank_ref(street):
            if loc_type == "ללא רחוב":
                flags_per_row[pos].append(("addr_empty", "כתובת ריקה — לא ניתן לגאוקוד", "block"))
            elif loc_type == "ציון דרך":
                flags_per_row[pos].append(("addr_desc", "כתובת תיאורית ללא רחוב מזוהה", "warn"))
            else:
                flags_per_row[pos].append(("addr_empty", "כתובת ריקה", addr_sev))
        elif _only_punct_or_num_ref(street):
            flags_per_row[pos].append(("addr_junk", "כתובת מכילה רק סימנים/מספרים", addr_sev))
        elif loc_type in DESCRIPTIVE_LOC_TYPES:
            pass

        if loc_type == "כתובת" and _is_blank_ref(row.get("מספר_בית")):
            flags_per_row[pos].append(("no_house", "חסר מספר בית", "warn"))

        cat = str(row.get("תת_נושא_חדש", "")).strip()
        if cat and cat not in KNOWN_CATEGORIES:
            flags_per_row[pos].append(("cat_unknown", "קטגוריה לא מזוהה", "warn"))

        if "סטטוס פנייה" in df.columns and _is_blank_ref(row.get("סטטוס פנייה")):
            flags_per_row[pos].append(("no_status", "חסר סטטוס", "warn"))

        if stage in ("geocode", "all"):
            lat = pd.to_numeric(str(row.get("קו_רוחב", "")).replace(",", ""), errors="coerce")
            lon = pd.to_numeric(str(row.get("קו_אורך", "")).replace(",", ""), errors="coerce")
            method = str(row.get("geocode_method", "")).strip()

            if pd.isna(lat) or pd.isna(lon):
                if loc_type not in DESCRIPTIVE_LOC_TYPES and method != "flagged_description":
                    flags_per_row[pos].append(("geo_fail", "לא גאוקודד", "block"))
            else:
                if not (HERZLIYA_BOUNDS["lat_min"] <= lat <= HERZLIYA_BOUNDS["lat_max"] and
                        HERZLIYA_BOUNDS["lon_min"] <= lon <= HERZLIYA_BOUNDS["lon_max"]):
                    flags_per_row[pos].append(("geo_outside", "מחוץ לגבולות הרצליה", "warn"))
                elif lon < SEA_LON_MAX:
                    flags_per_row[pos].append(("geo_sea", "נקודה נופלת בים", "warn"))

    df["_flags"] = flags_per_row
    df["_flag_labels"] = ["; ".join(f[1] for f in fl_) if fl_ else "" for fl_ in flags_per_row]
    df["_flag_severity"] = [
        ("block" if any(f[2] == "block" for f in fl_)
         else "warn" if fl_ else "")
        for fl_ in flags_per_row
    ]
    return df


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_flags(lst):
    """Sort flag tuples for order-independent comparison."""
    return sorted(lst)


def _assert_equal_flags(df_vec, df_ref, stage):
    """Assert that vectorized and reference outputs match on all rows."""
    for i, (idx, row_v) in enumerate(df_vec.iterrows()):
        row_r = df_ref.loc[idx]
        v_flags = _normalize_flags(row_v["_flags"])
        r_flags = _normalize_flags(row_r["_flags"])
        assert v_flags == r_flags, (
            f"Row {i} (stage={stage}): vectorized={v_flags} != reference={r_flags}"
        )
    pd.testing.assert_series_equal(
        df_vec["_flag_severity"].reset_index(drop=True),
        df_ref["_flag_severity"].reset_index(drop=True),
        check_names=False,
    )
    pd.testing.assert_series_equal(
        df_vec["_flag_labels"].reset_index(drop=True),
        df_ref["_flag_labels"].reset_index(drop=True),
        check_names=False,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_golden_clean_stage(df_enriched):
    """Vectorized output matches reference on enriched fixture at stage=clean."""
    df = df_enriched.copy()
    df_vec = fl.detect_flags(df.copy(), stage="clean")
    df_ref = detect_flags_ref(df.copy(), stage="clean")
    _assert_equal_flags(df_vec, df_ref, "clean")


def test_golden_geocode_stage(df_enriched):
    """Vectorized output matches reference on enriched fixture at stage=geocode."""
    df = df_enriched.copy()
    df_vec = fl.detect_flags(df.copy(), stage="geocode")
    df_ref = detect_flags_ref(df.copy(), stage="geocode")
    _assert_equal_flags(df_vec, df_ref, "geocode")


def test_golden_all_stage(df_enriched):
    """Vectorized output matches reference on enriched fixture at stage=all."""
    df = df_enriched.copy()
    df_vec = fl.detect_flags(df.copy(), stage="all")
    df_ref = detect_flags_ref(df.copy(), stage="all")
    _assert_equal_flags(df_vec, df_ref, "all")


def test_golden_with_date_range(df_enriched):
    """Vectorized output matches reference when date_min/max are supplied."""
    df = df_enriched.copy()
    df_vec = fl.detect_flags(df.copy(), date_min="2024-01-01", date_max="2024-12-31", stage="clean")
    df_ref = detect_flags_ref(df.copy(), date_min="2024-01-01", date_max="2024-12-31", stage="clean")
    _assert_equal_flags(df_vec, df_ref, "clean+dates")


def _make_large_frame(n: int) -> pd.DataFrame:
    """Synthetic n-row frame with the columns detect_flags reads."""
    streets = ["הבנים", "סוקולוב", "בן גוריון", "ויצמן", "הרצל",
               "ירושלים", "ז'בוטינסקי", "דיזנגוף", "אלנבי", "רוטשילד"]
    cats = list(fl.KNOWN_CATEGORIES)
    rows = []
    for i in range(n):
        rows.append({
            "מס' פניה": str(i + 1),
            "תאריך": "2024-06-15",
            "רחוב_ראשי": streets[i % len(streets)],
            "מספר_בית": str((i % 20) + 1),
            "סוג_מיקום": "כתובת",
            "רחוב_משני": "",
            "קו_רוחב": 32.16 + (i % 100) * 0.0001,
            "קו_אורך": 34.83 + (i % 100) * 0.0001,
            "geocode_method": "nominatim",
            "תת_נושא_חדש": cats[i % len(cats)],
            "סטטוס פנייה": "סגור",
        })
    return pd.DataFrame(rows)


def test_timing_17k_rows():
    """detect_flags on 17,000-row frame must complete in < 1.0 s."""
    df = _make_large_frame(17_000)
    t0 = time.perf_counter()
    fl.detect_flags(df, stage="all")
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, f"detect_flags took {elapsed:.2f}s on 17k rows (limit: 1.0s)"


def test_cache_key_deterministic(df_enriched):
    """flags_cache_key returns the same value on two calls with the same data."""
    k1 = fl.flags_cache_key(df_enriched)
    k2 = fl.flags_cache_key(df_enriched.copy())
    assert k1 == k2


def test_cache_key_changes_on_mutation(df_enriched):
    """flags_cache_key changes after a coordinate value is mutated."""
    k1 = fl.flags_cache_key(df_enriched)
    mutated = df_enriched.copy()
    coord_rows = mutated[mutated["קו_רוחב"].notna()]
    if len(coord_rows) == 0:
        pytest.skip("No coordinate rows in fixture")
    idx = coord_rows.index[0]
    mutated.at[idx, "קו_רוחב"] = 99.9999
    k2 = fl.flags_cache_key(mutated)
    assert k1 != k2
