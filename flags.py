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


def detect_flags(df: pd.DataFrame,
                 date_min: str = None, date_max: str = None,
                 stage: str = "clean") -> pd.DataFrame:
    """
    Return a DataFrame with two added columns:
      _flags       — list of (code, label, severity) per row
      _flag_labels — semicolon-joined Hebrew labels (for display)

    stage: 'clean' checks structural/address/quality; 'geocode' adds geocode
           checks; 'all' checks everything.
    """
    df = df.copy()
    flags_per_row = [[] for _ in range(len(df))]

    # ── Duplicate ticket IDs: intentionally not flagged ───────────────────
    # Duplicate IDs represent recurring calls on the same ticket, which is
    # captured analytically via מספר_חזרה / תלונה_חוזרת. Not a data error.

    # ── Date range (structural) ────────────────────────────────────────────
    if "תאריך" in df.columns and (date_min or date_max):
        dates = pd.to_datetime(df["תאריך"], errors="coerce")
        for pos, d in enumerate(dates):
            if pd.notna(d):
                if date_min and d < pd.to_datetime(date_min):
                    flags_per_row[pos].append(("date_early", "תאריך לפני התקופה", "warn"))
                if date_max and d > pd.to_datetime(date_max):
                    flags_per_row[pos].append(("date_late", "תאריך אחרי התקופה", "warn"))

    # ── Per-row field checks ───────────────────────────────────────────────
    for pos, (_, row) in enumerate(df.iterrows()):

        # Does this row already have valid coordinates? (used to clear address
        # blocks once geocoding has resolved them in a later stage)
        _lat = pd.to_numeric(str(row.get("קו_רוחב", "")).replace(",", ""), errors="coerce")
        _lon = pd.to_numeric(str(row.get("קו_אורך", "")).replace(",", ""), errors="coerce")
        has_coords = pd.notna(_lat) and pd.notna(_lon)
        # In clean stage, coordinates don't exist yet, so address issues always block.
        # In geocode/all stage, an address that got coordinates is considered resolved.
        addr_sev = "warn" if (stage in ("geocode", "all") and has_coords) else "block"

        # Missing required fields (structural, block)
        if "תאריך" in df.columns and _is_blank(row.get("תאריך")):
            flags_per_row[pos].append(("no_date", "חסר תאריך", "block"))
        if "מס' פניה" in df.columns and _is_blank(row.get("מס' פניה")):
            flags_per_row[pos].append(("no_id", "חסר מספר פניה", "block"))

        # Address issues
        loc_type = str(row.get("סוג_מיקום", "")).strip()
        street = row.get("רחוב_ראשי", "")
        raw_addr = row.get("כתובת ואתר/מוסד", "")

        if _is_blank(street):
            if loc_type == "ללא רחוב":
                # Truly blank with no street — block, nothing to geocode
                flags_per_row[pos].append(("addr_empty", "כתובת ריקה — לא ניתן לגאוקוד", "block"))
            elif loc_type == "ציון דרך":
                # Blank street but descriptive type — geocoder skips gracefully
                flags_per_row[pos].append(("addr_desc", "כתובת תיאורית ללא רחוב מזוהה", "warn"))
            else:
                flags_per_row[pos].append(("addr_empty", "כתובת ריקה", addr_sev))
        elif _only_punct_or_num(street):
            flags_per_row[pos].append(("addr_junk", "כתובת מכילה רק סימנים/מספרים", addr_sev))
        elif loc_type in DESCRIPTIVE_LOC_TYPES:
            # Non-blank street + ציון דרך: geocoder uses street centroid successfully.
            # Informational only — no flag.
            pass

        # Missing house number (address, warn — geocodes to street centroid)
        if loc_type == "כתובת" and _is_blank(row.get("מספר_בית")):
            flags_per_row[pos].append(("no_house", "חסר מספר בית", "warn"))

        # Data quality: unrecognized category
        cat = str(row.get("תת_נושא_חדש", "")).strip()
        if cat and cat not in KNOWN_CATEGORIES:
            flags_per_row[pos].append(("cat_unknown", "קטגוריה לא מזוהה", "warn"))

        # Data quality: unknown responsibility
        # א.מ.ל is a valid analytical outcome for ambiguous categories —
        # not a data error. No flag emitted.

        # Data quality: empty status
        if "סטטוס פנייה" in df.columns and _is_blank(row.get("סטטוס פנייה")):
            flags_per_row[pos].append(("no_status", "חסר סטטוס", "warn"))

        # ── Geocoding checks (stage geocode / all) ─────────────────────────
        if stage in ("geocode", "all"):
            lat = pd.to_numeric(str(row.get("קו_רוחב", "")).replace(",", ""), errors="coerce")
            lon = pd.to_numeric(str(row.get("קו_אורך", "")).replace(",", ""), errors="coerce")
            method = str(row.get("geocode_method", "")).strip()

            if pd.isna(lat) or pd.isna(lon):
                # Only block if it's a real address (descriptive already flagged above)
                if loc_type not in DESCRIPTIVE_LOC_TYPES and method != "flagged_description":
                    flags_per_row[pos].append(("geo_fail", "לא גאוקודד", "block"))
            else:
                if not (HERZLIYA_BOUNDS["lat_min"] <= lat <= HERZLIYA_BOUNDS["lat_max"] and
                        HERZLIYA_BOUNDS["lon_min"] <= lon <= HERZLIYA_BOUNDS["lon_max"]):
                    flags_per_row[pos].append(("geo_outside", "מחוץ לגבולות הרצליה", "warn"))
                elif lon < SEA_LON_MAX:
                    flags_per_row[pos].append(("geo_sea", "נקודה נופלת בים", "warn"))

    df["_flags"] = flags_per_row
    df["_flag_labels"] = ["; ".join(f[1] for f in fl) if fl else "" for fl in flags_per_row]
    df["_flag_severity"] = [
        ("block" if any(f[2] == "block" for f in fl)
         else "warn" if fl else "")
        for fl in flags_per_row
    ]
    return df


def count_blocking(df: pd.DataFrame) -> int:
    """Number of rows with at least one blocking flag."""
    if "_flag_severity" not in df.columns:
        return 0
    return int((df["_flag_severity"] == "block").sum())


def count_warnings(df: pd.DataFrame) -> int:
    """Number of rows with only warning flags."""
    if "_flag_severity" not in df.columns:
        return 0
    return int((df["_flag_severity"] == "warn").sum())


# Flag code → color (for highlighting)
FLAG_COLORS = {
    "block": "#fee2e2",   # red-100
    "warn":  "#fef3c7",   # amber-100
    "":      "",
}
