# -*- coding: utf-8 -*-
# ============================================================================
#  flags.py
#  עיריית הרצליה — זיהוי שורות הדורשות בדיקה ידנית
#  Herzliya Municipality — Row Flagging Logic
# ============================================================================
#
#  Detects rows that need human attention at each stage. Flags stay attached
#  to the row (never removed); the app highlights them in place and gates
#  progress until they're resolved.
#
#  FLAG CATEGORIES
#  ---------------
#   structural  — missing required field, duplicate ID, date out of range
#   address     — empty/punctuation-only, description-not-street, missing number
#   quality     — unrecognized category, empty responsibility/status, short text
#   geocode     — failed all passes, outside Herzliya, in the sea
#
#  Each flag is (code, hebrew_label, severity). Severity 'block' must be
#  resolved before advancing; 'warn' is advisory.
# ============================================================================

import re
import numpy as np
import pandas as pd

# Herzliya bounding box (approx) — points outside are suspicious
HERZLIYA_BOUNDS = {"lat_min": 32.14, "lat_max": 32.20, "lon_min": 34.78, "lon_max": 34.87}

# Sea box (west of the coastline) — Nominatim sometimes returns sea points
SEA_LON_MAX = 34.79  # west of this longitude at Herzliya latitudes is sea

# Known analytical categories (from clean_pipeline CATEGORY_MAP values)
KNOWN_CATEGORIES = {
    "אי פינוי", "תלונה על ביצוע הפינוי", "משטח מלוכלך", "פסולת לא מורשית",
    "כלי אצירה פגומים", "כלי אצירה מלא", "פגר", "פח נעלם", "בקשת ציוד ציבורי",
    "צואת כלבים", "פלישת צומח", "גראפיטי", "סחף אדמה", "בקשה מיוחדת לפינוי",
    "תביעת נזק",
}

# Location types that are inherently un-geocodable to a point
DESCRIPTIVE_LOC_TYPES = {"ציון דרך", "ללא רחוב"}


def _is_blank(v) -> bool:
    if pd.isna(v):
        return True
    s = str(v).strip()
    return s == "" or s.lower() in ("nan", "none")


def _only_punct_or_num(v) -> bool:
    if _is_blank(v):
        return False
    s = str(v).strip()
    return bool(re.fullmatch(r"[\d\s\.\,\-\_\!\?\(\)״׳'\"]+", s))


def _blank_mask(series: pd.Series) -> np.ndarray:
    """Vectorized blank check — True where value is blank/null/nan."""
    null_m = series.isna().to_numpy()
    str_m = series.astype(str).str.strip().str.lower().isin(["", "nan", "none"]).to_numpy()
    return null_m | str_m


def _punct_mask(series: pd.Series) -> np.ndarray:
    """Vectorized punctuation-only check — True where non-blank and only punct/digits."""
    s = series.fillna("").astype(str).str.strip()
    match_m = s.str.fullmatch(r"[\d\s\.\,\-\_\!\?\(\)״׳'\"]+", na=False).to_numpy()
    return match_m & ~_blank_mask(series)


def flags_cache_key(df: pd.DataFrame) -> tuple:
    """
    Cheap cache key for detect_flags results.
    Keyed on row count + hash of flag-relevant column values.
    """
    cols = [c for c in ("תאריך", "מס' פניה", "רחוב_ראשי", "מספר_בית", "סוג_מיקום",
                        "תת_נושא_חדש", "סטטוס פנייה", "קו_רוחב", "קו_אורך",
                        "geocode_method") if c in df.columns]
    key_str = df[cols].to_csv(index=False) if cols else str(len(df))
    return (len(df), hash(key_str))


def detect_flags(df: pd.DataFrame,
                 date_min: str = None, date_max: str = None,
                 stage: str = "clean") -> pd.DataFrame:
    """
    Return a DataFrame with two added columns:
      _flags       — list of (code, label, severity) per row
      _flag_labels — semicolon-joined Hebrew labels (for display)

    stage: 'clean' checks structural/address/quality; 'geocode' adds geocode
           checks; 'all' checks everything.

    Implementation uses vectorized pandas/numpy mask computation to stay fast
    on 17,000-row frames. Flag lists are assembled from mask indices only.
    """
    df = df.copy()
    n = len(df)

    # ── Precompute vectorized column arrays ──────────────────────────────────
    def _col(name, default=""):
        return df[name] if name in df.columns else pd.Series([default] * n, index=df.index)

    lat_num = pd.to_numeric(
        _col("קו_רוחב").astype(str).str.replace(",", "", regex=False), errors="coerce")
    lon_num = pd.to_numeric(
        _col("קו_אורך").astype(str).str.replace(",", "", regex=False), errors="coerce")
    has_coords = (lat_num.notna() & lon_num.notna()).to_numpy()

    street_s  = _col("רחוב_ראשי")
    loc_type_s = _col("סוג_מיקום").fillna("").astype(str).str.strip()
    method_s   = _col("geocode_method").fillna("").astype(str).str.strip()
    cat_s      = _col("תת_נושא_חדש").fillna("").astype(str).str.strip()
    house_s    = _col("מספר_בית")
    status_s   = _col("סטטוס פנייה")
    date_s     = _col("תאריך")
    ticket_s   = _col("מס' פניה")

    loc_type_arr  = loc_type_s.to_numpy()
    method_arr    = method_s.to_numpy()

    # addr_sev: "warn" when stage=geocode/all AND has_coords, else "block"
    use_warn_sev = (stage in ("geocode", "all")) and True
    addr_sev_arr = np.where(use_warn_sev & has_coords, "warn", "block")

    # ── Compute flag masks (all vectorized) ──────────────────────────────────
    # structural
    no_date_mask  = _blank_mask(date_s)   if "תאריך"      in df.columns else np.zeros(n, bool)
    no_id_mask    = _blank_mask(ticket_s) if "מס' פניה"   in df.columns else np.zeros(n, bool)

    # date range
    date_early_mask = np.zeros(n, bool)
    date_late_mask  = np.zeros(n, bool)
    if "תאריך" in df.columns and (date_min or date_max):
        dates = pd.to_datetime(date_s, errors="coerce")
        if date_min:
            date_early_mask = (dates.notna() & (dates < pd.to_datetime(date_min))).to_numpy()
        if date_max:
            date_late_mask  = (dates.notna() & (dates > pd.to_datetime(date_max))).to_numpy()

    # address
    street_blank = _blank_mask(street_s)
    street_punct = _punct_mask(street_s)

    loc_no_street  = (loc_type_arr == "ללא רחוב")
    loc_landmark   = (loc_type_arr == "ציון דרך")
    loc_is_address = (loc_type_arr == "כתובת")
    no_house_mask  = loc_is_address & _blank_mask(house_s)

    # addr_empty: blank street with loc_type == ללא רחוב (always block)
    addr_empty_block = street_blank & loc_no_street
    # addr_desc: blank street with loc_type == ציון דרך (always warn)
    addr_desc_mask   = street_blank & loc_landmark
    # addr_empty: blank street (other) — severity from addr_sev_arr
    addr_empty_other = street_blank & ~loc_no_street & ~loc_landmark
    # addr_junk: non-blank, punct-only
    addr_junk_mask   = street_punct

    # quality
    no_status_mask = (("סטטוס פנייה" in df.columns) and
                      _blank_mask(status_s)) if "סטטוס פנייה" in df.columns else np.zeros(n, bool)
    cat_arr        = cat_s.to_numpy()
    cat_unknown_mask = np.array([(c != "" and c not in KNOWN_CATEGORIES) for c in cat_arr])

    # geocode
    geo_fail_mask    = np.zeros(n, bool)
    geo_outside_mask = np.zeros(n, bool)
    geo_sea_mask     = np.zeros(n, bool)
    if stage in ("geocode", "all"):
        no_coords = ~has_coords
        real_addr = ~np.isin(loc_type_arr, list(DESCRIPTIVE_LOC_TYPES)) & (method_arr != "flagged_description")
        geo_fail_mask    = no_coords & real_addr
        in_bounds = (
            (lat_num >= HERZLIYA_BOUNDS["lat_min"]) & (lat_num <= HERZLIYA_BOUNDS["lat_max"]) &
            (lon_num >= HERZLIYA_BOUNDS["lon_min"]) & (lon_num <= HERZLIYA_BOUNDS["lon_max"])
        ).to_numpy()
        geo_outside_mask = has_coords & ~in_bounds
        geo_sea_mask     = has_coords & in_bounds & (lon_num < SEA_LON_MAX).to_numpy()

    # ── Assemble per-row flag lists from mask indices ────────────────────────
    flags_per_row: list = [[] for _ in range(n)]

    def _add_flag(mask, code, label, sev):
        for pos in np.where(mask)[0]:
            flags_per_row[pos].append((code, label, sev))

    def _add_flag_var_sev(mask, code, label, sev_arr):
        for pos in np.where(mask)[0]:
            flags_per_row[pos].append((code, label, sev_arr[pos]))

    _add_flag(no_date_mask,     "no_date",    "חסר תאריך",             "block")
    _add_flag(no_id_mask,       "no_id",      "חסר מספר פניה",         "block")
    _add_flag(date_early_mask,  "date_early", "תאריך לפני התקופה",     "warn")
    _add_flag(date_late_mask,   "date_late",  "תאריך אחרי התקופה",     "warn")

    _add_flag(addr_empty_block, "addr_empty", "כתובת ריקה — לא ניתן לגאוקוד", "block")
    _add_flag(addr_desc_mask,   "addr_desc",  "כתובת תיאורית ללא רחוב מזוהה", "warn")
    _add_flag_var_sev(addr_empty_other, "addr_empty", "כתובת ריקה",    addr_sev_arr)
    _add_flag_var_sev(addr_junk_mask,   "addr_junk",  "כתובת מכילה רק סימנים/מספרים", addr_sev_arr)

    _add_flag(no_house_mask,    "no_house",   "חסר מספר בית",          "warn")
    _add_flag(cat_unknown_mask, "cat_unknown","קטגוריה לא מזוהה",      "warn")
    if "סטטוס פנייה" in df.columns:
        _add_flag(no_status_mask, "no_status", "חסר סטטוס",           "warn")

    _add_flag(geo_fail_mask,    "geo_fail",   "לא גאוקודד",            "block")
    _add_flag(geo_outside_mask, "geo_outside","מחוץ לגבולות הרצליה",  "warn")
    _add_flag(geo_sea_mask,     "geo_sea",    "נקודה נופלת בים",       "warn")

    df["_flags"] = flags_per_row
    df["_flag_labels"] = ["; ".join(f[1] for f in fl) if fl else "" for fl in flags_per_row]
    df["_flag_severity"] = [
        ("block" if any(f[2] == "block" for f in fl)
         else "warn" if fl else "")
        for fl in flags_per_row
    ]
    return df


# Three-level severity scale: block > review/warn > info > ""
# "warn" and "review" are treated as synonyms so existing data is compatible.
SEVERITY_BLOCK  = "block"
SEVERITY_REVIEW = "warn"   # canonical internal value; alias: "review"
SEVERITY_INFO   = "info"


def count_blocking(df: pd.DataFrame) -> int:
    """Number of rows with at least one blocking flag."""
    if "_flag_severity" not in df.columns:
        return 0
    return int((df["_flag_severity"] == SEVERITY_BLOCK).sum())


def count_warnings(df: pd.DataFrame) -> int:
    """Number of rows with only warning/review flags."""
    if "_flag_severity" not in df.columns:
        return 0
    return int(df["_flag_severity"].isin([SEVERITY_REVIEW, "review"]).sum())


def count_review(df: pd.DataFrame) -> int:
    """Alias for count_warnings — rows flagged for human review (non-blocking)."""
    return count_warnings(df)


def count_info(df: pd.DataFrame) -> int:
    """Number of rows with only informational flags."""
    if "_flag_severity" not in df.columns:
        return 0
    return int((df["_flag_severity"] == SEVERITY_INFO).sum())


def build_triage_groups(flagged: pd.DataFrame) -> dict:
    """
    Partition flagged DataFrame into named triage groups for display.

    Returns an ordered dict:
      "blocking"   → rows where _flag_severity == "block"
      "review"     → rows where _flag_severity in ("warn", "review")
      "info"       → rows where _flag_severity == "info"
      "clean"      → rows with no flags

    Each value is a pd.DataFrame (subset of flagged, with flag columns included).
    Groups are ordered block → review → info → clean so the UI can render them
    in priority order without sorting.
    """
    if "_flag_severity" not in flagged.columns:
        return {"blocking": pd.DataFrame(), "review": pd.DataFrame(),
                "info": pd.DataFrame(), "clean": flagged.copy()}

    sev = flagged["_flag_severity"]
    return {
        "blocking": flagged[sev == SEVERITY_BLOCK].copy(),
        "review":   flagged[sev.isin([SEVERITY_REVIEW, "review"])].copy(),
        "info":     flagged[sev == SEVERITY_INFO].copy(),
        "clean":    flagged[sev == ""].copy(),
    }


def triage_summary(groups: dict) -> dict:
    """Return count per group from build_triage_groups output."""
    return {k: len(v) for k, v in groups.items()}


def waived_tickets(flagged: pd.DataFrame) -> list:
    """Return ticket IDs for all blocking rows (used when logging a waive override)."""
    if "_flag_severity" not in flagged.columns or "מס' פניה" not in flagged.columns:
        return []
    return flagged.loc[flagged["_flag_severity"] == SEVERITY_BLOCK, "מס' פניה"].tolist()


# Flag code → color (for highlighting)
FLAG_COLORS = {
    "block":  "#fee2e2",   # red-100
    "warn":   "#fef3c7",   # amber-100
    "review": "#fef3c7",   # amber-100 (synonym of warn)
    "info":   "#eff6ff",   # blue-50
    "":       "",
}
