# -*- coding: utf-8 -*-
# ============================================================================
#  enrich_pipeline.py
#  עיריית הרצליה — העשרת נתונים: רובע פינוי, יום פינוי, תלונה ביום פינוי
#  Herzliya Municipality — Zone Enrichment Pipeline
# ============================================================================
#
#  WHAT THIS DOES
#  --------------
#  Takes a geocoded DataFrame and adds three columns:
#    • רובע_פינוי        — collection zone (from coordinates)
#    • יום_פינוי          — collection weekday (determined by zone)
#    • תלונה_ביום_פינוי  — 1 if the complaint fell on the zone's collection day
#
#  HOW ZONES ARE ASSIGNED
#  ----------------------
#  The original zone boundaries came from a municipal collection-zone GeoJSON
#  (point-in-polygon). That polygon file is not bundled here. Instead, this
#  module reproduces the assignment from 1,656 labeled reference points
#  (zone_reference.csv) using a 1-nearest-neighbor classifier. On the original
#  17,208-row dataset this reproduces the polygon zones at 100% accuracy,
#  including the "הרצליה ב" carve-out. Points that fall nearest to the
#  out-of-bounds reference cluster are labeled "מחוץ לתחום".
#
#  NOTE (documented limitation): if the municipality provides the official
#  collection-zone GeoJSON, swap the KNN step for a true point-in-polygon test.
#
#  USAGE
#  -----
#    from enrich_pipeline import enrich_dataframe
#    df_enriched, stats = enrich_dataframe(df_geocoded)
#
# ============================================================================

import os
import logging
import pandas as pd
import numpy as np

log = logging.getLogger("enrich_pipeline")

try:
    from sklearn.neighbors import KNeighborsClassifier
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

# ── Column names ────────────────────────────────────────────────────────────
LAT_COL   = "קו_רוחב"
LON_COL   = "קו_אורך"
ZONE_COL  = "רובע_פינוי"
DAY_COL   = "יום_פינוי"
SAMEDAY_COL = "תלונה_ביום_פינוי"
COMPLAINT_DAY_COL = "יום"   # weekday name the complaint was filed

# ── Zone → collection weekday (deterministic) ───────────────────────────────
ZONE_TO_DAY = {
    "מרכז":       "שני",
    "צפון":       "שני",
    "דרום":       "שלישי",
    "הרצליה ב":   "שלישי",
    "מזרח":       "רביעי",
    "מערב":       "רביעי",
    "מחוץ לתחום": None,
    "לא ידוע":    None,
}

# ── Reference file location ─────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
REFERENCE_FILE = os.path.join(_HERE, "zone_reference.csv")

# Module-level cached classifier
_classifier = None
_ref_loaded = False


def _load_classifier():
    """Load and cache the KNN zone classifier from the reference file."""
    global _classifier, _ref_loaded
    if _ref_loaded:
        return _classifier

    _ref_loaded = True

    if not HAS_SKLEARN:
        log.warning("scikit-learn not installed — zone enrichment unavailable")
        _classifier = None
        return None

    if not os.path.exists(REFERENCE_FILE):
        log.warning(f"Zone reference file not found: {REFERENCE_FILE}")
        _classifier = None
        return None

    ref = pd.read_csv(REFERENCE_FILE, encoding="utf-8-sig")
    knn = KNeighborsClassifier(n_neighbors=1)
    knn.fit(ref[["lat", "lon"]].values, ref["zone"].values)
    _classifier = knn
    log.info(f"Zone classifier loaded ({len(ref):,} reference points)")
    return knn


def enrich_dataframe(df: pd.DataFrame) -> tuple:
    """
    Add zone, collection-day, and same-day-flag columns to a geocoded DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Must have קו_רוחב, קו_אורך (coordinates) and יום (complaint weekday).

    Returns
    -------
    (df, stats) : tuple
    """
    df = df.copy()

    # Ensure coordinate columns are numeric (strip stray commas)
    for col in (LAT_COL, LON_COL):
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "").str.strip(),
                errors="coerce",
            )

    # Initialise output columns
    df[ZONE_COL] = "לא ידוע"
    df[DAY_COL] = None
    df[SAMEDAY_COL] = np.nan

    clf = _load_classifier()

    has_coords = df[LAT_COL].notna() & df[LON_COL].notna()

    if clf is not None and has_coords.any():
        coords = df.loc[has_coords, [LAT_COL, LON_COL]].values
        predicted = clf.predict(coords)
        df.loc[has_coords, ZONE_COL] = predicted
    elif clf is None:
        log.warning("No classifier available — all zones set to 'לא ידוע'")

    # Assign collection day from zone
    df[DAY_COL] = df[ZONE_COL].map(ZONE_TO_DAY)

    # Same-day flag: 1 if complaint weekday matches collection weekday
    if COMPLAINT_DAY_COL in df.columns:
        both_known = df[DAY_COL].notna() & df[COMPLAINT_DAY_COL].notna()
        df.loc[both_known, SAMEDAY_COL] = (
            df.loc[both_known, COMPLAINT_DAY_COL].astype(str).str.strip()
            == df.loc[both_known, DAY_COL].astype(str).str.strip()
        ).astype(int)

    # Stats
    zone_counts = df[ZONE_COL].value_counts(dropna=False).to_dict()
    total = len(df)
    in_city = int((~df[ZONE_COL].isin(["לא ידוע", "מחוץ לתחום"])).sum())
    same_day = int((df[SAMEDAY_COL] == 1).sum())
    same_day_pct = round(same_day / total * 100, 1) if total else 0

    stats = {
        "total_rows":     total,
        "in_city":        in_city,
        "in_city_pct":    round(in_city / total * 100, 1) if total else 0,
        "same_day":       same_day,
        "same_day_pct":   same_day_pct,
        "zone_counts":    zone_counts,
    }

    log.info(f"Enrichment complete: {in_city}/{total} in-city, "
             f"{same_day} same-day complaints ({same_day_pct}%)")

    return df, stats


# ── Standalone CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) < 2:
        print("Usage: python enrich_pipeline.py input.xlsx [output.xlsx]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace(".xlsx", "_enriched.xlsx")

    print(f"Loading {input_file}...")
    df = pd.read_excel(input_file)
    print(f"  {len(df):,} rows loaded")

    df, stats = enrich_dataframe(df)

    print(f"\n{'='*50}")
    print(f"ENRICHMENT RESULTS")
    print(f"{'='*50}")
    print(f"  Total rows:    {stats['total_rows']:,}")
    print(f"  In-city:       {stats['in_city']:,} ({stats['in_city_pct']}%)")
    print(f"  Same-day:      {stats['same_day']:,} ({stats['same_day_pct']}%)")
    print(f"\n  Zones:")
    for zone, count in sorted(stats['zone_counts'].items(), key=lambda x: -x[1]):
        print(f"    {zone:12s} {count:,}")
    print(f"{'='*50}")

    df.to_excel(output_file, index=False)
    print(f"\nSaved to {output_file}")
