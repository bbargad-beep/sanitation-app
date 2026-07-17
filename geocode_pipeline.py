# -*- coding: utf-8 -*-
# ============================================================================
#  geocode_pipeline.py
#  עיריית הרצליה — צינור גאוקוד מאוחד
#  Herzliya Municipality — Consolidated Geocoding Pipeline
# ============================================================================
#
#  WHAT THIS DOES
#  --------------
#  Takes a cleaned DataFrame (output of clean_pipeline) and geocodes every row
#  through a multi-pass cascade, maximising automatic coverage before surfacing
#  any remaining rows for manual correction.
#
#  PASS ORDER
#  ----------
#    1. Nominatim  — candidate cascade (original → stripped → expanded → corrected)
#    2. OSM street centroids — baked-in offline lookup for known Herzliya streets
#    3. GIS portal rescue — Playwright auto-token → exact / nearest / centroid
#    4. Returns unresolved rows — for the manual correction UI in the app
#
#  USAGE (in-memory, from app.py)
#  ------
#    from geocode_pipeline import geocode_dataframe
#    df_geocoded, stats = geocode_dataframe(df_clean, progress_callback=fn)
#
#  USAGE (standalone)
#  ------
#    python geocode_pipeline.py input.xlsx output.xlsx
#
# ============================================================================

import os
import re
import time
import logging
import urllib.parse
import uuid
from typing import Optional, Callable

import pandas as pd
import numpy as np

# Optional imports — graceful degradation
try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut, GeocoderServiceError
    HAS_GEOPY = True
except ImportError:
    HAS_GEOPY = False

try:
    from pyproj import Transformer
    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import difflib
    HAS_DIFFLIB = True
except ImportError:
    HAS_DIFFLIB = False

log = logging.getLogger("geocode_pipeline")

# ============================================================================
#  CONFIGURATION
# ============================================================================

PIPELINE_VERSION = "3.0.0"
NOMINATIM_DELAY = 1.1       # seconds between Nominatim requests (rate limit)
GIS_DELAY       = 0.4       # seconds between GIS portal requests
NOMINATIM_AGENT = "herzliya_sanitation_municipal_app"
PRECISION_COL   = "דיוק_גאוקוד"

# Herzliya bounding box (approx) for sanity-checking geocode results
HERZLIYA_BOUNDS = {
    "lat_min": 32.14,  "lat_max": 32.20,
    "lon_min": 34.78,  "lon_max": 34.87,
}

# ============================================================================
#  STREET NAME CORRECTIONS — loaded from corrections.json
# ============================================================================
from corrections import (
    STREET_CORRECTIONS,
    GIS_MANUAL_MAP as _GIS_MAP_FROM_JSON,
    FLAG_DESCRIPTIONS as _FLAG_DESC_FROM_JSON,
    KNOWN_UNRESOLVABLE,
)

# ============================================================================
#  BAKED-IN OSM STREET CENTROIDS (from Overpass query)
#  Offline fallback — no API calls needed
# ============================================================================

STREET_COORDS = {
    'אבניים': (32.16371, 34.850203),
    'אוטו ורבורג': (32.156375, 34.844152),
    'אופיר סמטה': (32.174387, 34.845778),
    'אור חיים': (32.172397, 34.83291),
    'אירוסים': (32.167343, 34.817444),
    'אלט נויילנד': (32.155707, 34.801055),
    'אלי לנדאו עד נילי': (32.168428, 34.800488),
    'אנילביץ מרדכי': (32.175053, 34.847837),
    'אנצו סירני': (32.165213, 34.806525),
    'ארגוב סשה': (32.17347, 34.841234),
    'אריה לייב יפה': (32.171197, 34.845379),
    'בית הראשונים': (32.168166, 34.841869),
    'בראון': (32.167829, 34.817541),
    'גולומב אליהו': (32.173929, 34.84728),
    'גיבורי עציון': (32.164022, 34.858076),
    'דפנה האשל': (32.180214, 34.808347),
    'האסיף': (32.180047, 34.842885),
    'הבריגדה היהודית': (32.176266, 34.849103),
    'הגדעונים': (32.17923, 34.812754),
    'הדודאים שביל אדמית': (32.152888, 34.84922),
    'הדסים': (32.176947, 34.847935),
    'המעין': (32.168376, 34.852304),
    'המעפילים': (32.181628, 34.812623),
    'הס': (32.164708, 34.841489),
    'הקדמה': (32.184253, 34.811576),
    'הראובני דוד': (32.164239, 34.834635),
    'הרב נורוק': (32.154833, 34.840871),
    'הרב פישמן': (32.17206, 34.815768),
    'הרימונים': (32.178767, 34.846385),
    'הרצוג': (32.168058, 34.84649),
    'ווינגיט': (32.176475, 34.80566),
    'זהר טל': (32.171704, 34.8028),
    'זיסו א.ל.': (32.177267, 34.854528),
    'חנה רובינא': (32.165581, 34.829496),
    'חפצי בה': (32.157511, 34.848938),
    'חתם סופר': (32.152253, 34.843559),
    'טשרנחובסקי': (32.169628, 34.841086),
    'יגאל אלון': (32.168939, 34.847209),
    'יהושוע בן נון': (32.165462, 34.8055),
    'יהושפט המלך מול': (32.170268, 34.808081),
    'לחי': (32.173967, 34.805458),
    'מדינת היהודים': (32.166997, 34.807884),
    'מוהוליבר': (32.165992, 34.850023),
    'מורי עפארי': (32.16102, 34.85816),
    'מנחם בגין שד': (32.178202, 34.831661),
    'מרזוק משה': (32.17753, 34.852925),
    'מרים החשמונאית': (32.160557, 34.850698),
    'מתיתיהו': (32.166956, 34.804054),
    'נוה עובד': (32.182418, 34.812901),
    'סירקין': (32.166446, 34.845646),
    'סנה משה': (32.161518, 34.851108),
    'פתח תקוה': (32.159748, 34.851381),
    'צבעוני': (32.152082, 34.850024),
    'קהילת ציון': (32.164253, 34.84904),
    "קורצ'ק יאנוש": (32.174184, 34.847173),
    'קפלינסקי': (32.171675, 34.847599),
    'רזיאל דוד': (32.157691, 34.849499),
    'רייק חביבה': (32.165503, 34.80694),
    'רפי וקנין': (32.169704, 34.861609),
    'שביל אבו חצירא שירת גאולים': (32.154305, 34.837483),
    'שד אלי לנדאו': (32.168428, 34.800488),
    'שד יעקב לנצט': (32.165455, 34.841825),
    'שוידלסון': (32.161177, 34.843567),
    'שחל': (32.16258, 34.856693),
    'שלום רוזנלפלד': (32.161286, 34.828979),
    'שלומית כהן-קישיק': (32.160343, 34.831403),
}

# ============================================================================
#  GIS PORTAL CONFIGURATION (Herzliya municipal GIS)
# ============================================================================

GIS_PROXY_BASE  = "https://v5.gis-net.co.il/proxy/proxy.ashx"
GIS_ARCGIS_PATH = "http://arcgis005/arcgis/rest/services/Herzliya/herzliya_main_date1/MapServer/11/query"
GIS_HOME_URL    = "https://v5.gis-net.co.il/v5/Hertzeliya?minisite=public"
GIS_HEADERS     = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer":    GIS_HOME_URL,
}

GIS_MANUAL_MAP = _GIS_MAP_FROM_JSON
FLAG_DESCRIPTIONS = _FLAG_DESC_FROM_JSON



# ============================================================================
#  OFFICIAL STREET REGISTRY  (קוד רחוב.xlsx)
#  Herzliya municipal street list — 770 canonical names + street codes.
#  Names are stored in family-name-first order, matching the GIS portal's
#  street_nam field.  Used to auto-resolve CRM name variants without needing
#  manual additions to GIS_MANUAL_MAP or STREET_CORRECTIONS.
# ============================================================================

def _load_street_registry() -> dict:
    """Load {canonical_name: street_code} from קוד רחוב.xlsx."""
    try:
        path = os.path.join(os.path.dirname(__file__), '..', 'muni data integration', 'קוד רחוב.xlsx')
        df = pd.read_excel(path, header=None, usecols=[0, 1])
        df.columns = ['name', 'code']
        df['name'] = df['name'].astype(str).str.strip()
        df['code'] = pd.to_numeric(df['code'], errors='coerce')
        df = df[df['code'].notna() & (df['code'] > 0)].copy()
        df['code'] = df['code'].astype(int)
        result = dict(zip(df['name'], df['code']))
        log.info(f"Street registry loaded: {len(result)} streets")
        return result
    except Exception as e:
        log.warning(f"Street registry not loaded: {e}")
        return {}

STREET_REGISTRY: dict = _load_street_registry()
_REGISTRY_NAMES: list = list(STREET_REGISTRY.keys())


def _registry_resolve(name: str):
    """
    Resolve a name to its official registry canonical form and street code.

    Strategy (in order):
      1. Exact match
      2. Word-set match — same tokens, any order (catches "חנה רובינא" ↔ "רובינא חנה")
      3. Fuzzy match via difflib (cutoff 0.85, conservative to avoid false positives)

    Returns (canonical_name, street_code) or (None, None).
    """
    if not _REGISTRY_NAMES:
        return None, None
    name = name.strip()

    # 1. Exact
    if name in STREET_REGISTRY:
        return name, STREET_REGISTRY[name]

    # 2. Word-set (order-insensitive — resolves person-name reversals reliably)
    name_words = frozenset(name.split())
    if len(name_words) >= 2:
        for cand in _REGISTRY_NAMES:
            if frozenset(cand.split()) == name_words:
                return cand, STREET_REGISTRY[cand]

    # 3. Fuzzy
    if HAS_DIFFLIB and len(name) >= 3:
        matches = difflib.get_close_matches(name, _REGISTRY_NAMES, n=1, cutoff=0.85)
        if matches:
            canon = matches[0]
            return canon, STREET_REGISTRY[canon]

    return None, None


# ============================================================================
#  NOMINATIM PASS — candidate cascade
# ============================================================================

def _nominatim_geocode_one(geolocator, query: str, retries: int = 2):
    """Single Nominatim query. Returns (lat, lon, place_rank, addresstype)."""
    for attempt in range(retries):
        try:
            result = geolocator.geocode(query, language="he", timeout=10)
            if result:
                raw = getattr(result, "raw", {}) or {}
                place_rank = raw.get("place_rank")
                addresstype = raw.get("addresstype", "")
                return (round(result.latitude, 6), round(result.longitude, 6),
                        place_rank, addresstype)
            return None, None, None, None
        except (GeocoderTimedOut, GeocoderServiceError):
            if attempt < retries - 1:
                time.sleep(2)
    return None, None, None, None


def _build_candidates(street: str, house_num: str = "",
                      loc_type: str = "", secondary_street: str = "") -> list:
    """
    Build an ordered list of Nominatim query strings from most to least specific.
    General-purpose: works for any CRM export, not hard-coded to specific rows.
    """
    candidates = []
    street = street.strip()
    num = house_num.strip() if house_num and str(house_num).strip() not in ("", "nan", "None", "0") else ""

    def _add(st, n=""):
        q = f"{st} {n}".strip() + ", הרצליה, ישראל"
        q = q.replace("  ", " ").replace(" ,", ",")
        if q not in candidates:
            candidates.append(q)

    # ── Special handling for intersections ─────────────────────────────────
    if loc_type == "צומת" and secondary_street:
        _add(f"{street} פינת {secondary_street}")
        _add(street)
        _add(secondary_street)
        return candidates

    # ── Special handling for house ranges ──────────────────────────────────
    if loc_type == "טווח בתים" and num and "-" in num:
        try:
            parts = num.split("-")
            mid = (int(parts[0].strip()) + int(parts[1].strip())) // 2
            _add(street, str(mid))
        except ValueError:
            pass
        _add(street, parts[0].strip())
        _add(street)
        return candidates

    # ── 1. Original form with house number ────────────────────────────────
    _add(street, num)

    # ── 2. Strip apartment/floor/entrance suffixes ────────────────────────
    cleaned_num = num
    if num:
        cleaned_num = re.sub(r'[/\\]\s*\d+$', '', num).strip()       # 5/2 → 5
        cleaned_num = re.sub(r'\s*דירה\s*\d*', '', cleaned_num)       # דירה 3
        cleaned_num = re.sub(r'\s*קומה\s*\d*', '', cleaned_num)       # קומה 2
        cleaned_num = re.sub(r'\s*כניסה\s*\w*', '', cleaned_num)      # כניסה ב
        cleaned_num = cleaned_num.strip()
        if cleaned_num != num and cleaned_num:
            _add(street, cleaned_num)

    # ── 3. Strip geresh/gershayim characters ──────────────────────────────
    stripped = street.replace('"', '').replace("'", '').replace('״', '').replace('׳', '')
    if stripped != street:
        _add(stripped, num)
        _add(stripped, cleaned_num if cleaned_num != num else "")
        _add(stripped)

    # ── 4. Strip dots (abbreviations like י.ל.גורדון) ─────────────────────
    no_dots = street.replace(".", " ").strip()
    no_dots = re.sub(r'\s+', ' ', no_dots)
    if no_dots != street:
        _add(no_dots, num)
        _add(no_dots)

    # ── 5. Expand common prefixes ─────────────────────────────────────────
    expanded = street
    expanded = re.sub(r'^שד\b\.?\s*', 'שדרות ', expanded).strip()
    expanded = re.sub(r'^רח\b\.?\s*', 'רחוב ', expanded).strip()
    expanded = re.sub(r"^כ'\s*", 'כביש ', expanded).strip()
    expanded = re.sub(r'^דר\b\.?\s*', 'דרך ', expanded).strip()
    if expanded != street:
        _add(expanded, num)
        _add(expanded)

    # ── 6. Known corrections (general, not dataset-specific) ──────────────
    norm_key = re.sub(r'[".׳״\'"]', '', street).replace(".", "").strip()
    corrected = STREET_CORRECTIONS.get(norm_key) or STREET_CORRECTIONS.get(street)
    if corrected and corrected != street:
        _add(corrected, num)
        _add(corrected)

    # ── 7. Street-only fallback (no house number) ─────────────────────────
    _add(street)
    if stripped != street:
        _add(stripped)
    if no_dots != street:
        _add(no_dots)
    if expanded != street:
        _add(expanded)

    return candidates


def _is_in_herzliya(lat, lon) -> bool:
    """Check if coordinates fall within Herzliya's approximate bounding box."""
    return (HERZLIYA_BOUNDS["lat_min"] <= lat <= HERZLIYA_BOUNDS["lat_max"] and
            HERZLIYA_BOUNDS["lon_min"] <= lon <= HERZLIYA_BOUNDS["lon_max"])


def nominatim_pass(df: pd.DataFrame,
                   progress_cb: Optional[Callable] = None,
                   checkpoint_cb: Optional[Callable] = None,
                   checkpoint_every: int = 100) -> pd.DataFrame:
    """
    Run Nominatim geocoding on all rows missing coordinates.
    Modifies df in place, adding קו_רוחב, קו_אורך, geocode_method columns.
    Uses a per-street cache to avoid repeat queries for the same street.
    """
    if not HAS_GEOPY:
        log.warning("geopy not installed — skipping Nominatim pass")
        return df

    geolocator = Nominatim(user_agent=NOMINATIM_AGENT)

    # Ensure columns exist
    for col in ["קו_רוחב", "קו_אורך", "geocode_method", PRECISION_COL,
                "geocode_query"]:
        if col not in df.columns:
            df[col] = None

    # Identify rows needing geocoding
    mask = df["קו_רוחב"].isna() | (df["קו_רוחב"].astype(str).str.strip() == "")
    to_geocode = df[mask].index.tolist()
    total = len(to_geocode)

    if total == 0:
        log.info("Nominatim: all rows already have coordinates")
        return df

    log.info(f"Nominatim: {total} rows to geocode")

    # Cache: (street, house_num) → (lat, lon, place_rank, query) to avoid re-querying
    cache = {}
    geocoded = 0
    failed = 0

    for i, idx in enumerate(to_geocode):
        row = df.loc[idx]
        street = str(row.get("רחוב_ראשי", "")).strip() if pd.notna(row.get("רחוב_ראשי")) else ""
        num = str(row.get("מספר_בית", "")).strip() if pd.notna(row.get("מספר_בית")) else ""
        loc_type = str(row.get("סוג_מיקום", "")).strip() if pd.notna(row.get("סוג_מיקום")) else ""
        st2 = str(row.get("רחוב_משני", "")).strip() if pd.notna(row.get("רחוב_משני")) else ""

        def _fire_checkpoint():
            if checkpoint_cb and (i + 1) % checkpoint_every == 0:
                checkpoint_cb(df)

        if not street or street == "nan":
            df.at[idx, "geocode_method"] = "no_street"
            df.at[idx, PRECISION_COL] = "none"
            failed += 1
            _fire_checkpoint()
            continue

        # Flag descriptions (not real addresses)
        if street in FLAG_DESCRIPTIONS:
            df.at[idx, "geocode_method"] = "flagged_description"
            df.at[idx, PRECISION_COL] = "none"
            failed += 1
            _fire_checkpoint()
            continue

        # Check cache
        cache_key = (street, num, loc_type, st2)
        if cache_key in cache:
            hit = cache[cache_key]
            if hit["lat"] is not None:
                df.at[idx, "קו_רוחב"] = hit["lat"]
                df.at[idx, "קו_אורך"] = hit["lon"]
                df.at[idx, "geocode_method"] = "nominatim_cached"
                df.at[idx, PRECISION_COL] = hit["precision"]
                df.at[idx, "geocode_query"] = hit["query"]
                geocoded += 1
            else:
                df.at[idx, PRECISION_COL] = "none"
                failed += 1
            _fire_checkpoint()
            continue

        # Build candidates and try each
        candidates = _build_candidates(street, num, loc_type, st2)
        lat, lon, place_rank = None, None, None
        matched_query = None

        for query in candidates:
            lat, lon, pr, _ = _nominatim_geocode_one(geolocator, query)
            time.sleep(NOMINATIM_DELAY)

            if lat is not None:
                if _is_in_herzliya(lat, lon):
                    place_rank = pr
                    matched_query = query
                    break
                else:
                    lat, lon, place_rank = None, None, None

        precision = "none"
        if lat is not None:
            precision = "address" if place_rank == 30 else "street"

        cache[cache_key] = {"lat": lat, "lon": lon, "precision": precision,
                            "query": matched_query}

        if lat is not None:
            df.at[idx, "קו_רוחב"] = lat
            df.at[idx, "קו_אורך"] = lon
            df.at[idx, "geocode_method"] = "nominatim"
            df.at[idx, PRECISION_COL] = precision
            df.at[idx, "geocode_query"] = matched_query
            geocoded += 1
        else:
            df.at[idx, PRECISION_COL] = "none"
            failed += 1

        if progress_cb and (i + 1) % 10 == 0:
            progress_cb("nominatim", i + 1, total, geocoded, failed)

        _fire_checkpoint()

    log.info(f"Nominatim: geocoded {geocoded}, failed {failed}")
    if progress_cb:
        progress_cb("nominatim", total, total, geocoded, failed)

    return df


# ============================================================================
#  OSM CENTROID PASS — offline baked-in lookup
# ============================================================================

def osm_centroid_pass(df: pd.DataFrame) -> pd.DataFrame:
    """
    For rows still missing coordinates, try the baked-in OSM street centroids.
    This is a street-level fallback (no house-number precision).
    """
    for col in ["קו_רוחב", "קו_אורך", "geocode_method", PRECISION_COL,
                "geocode_query"]:
        if col not in df.columns:
            df[col] = None

    mask = df["קו_רוחב"].isna() | (df["קו_רוחב"].astype(str).str.strip() == "")
    to_rescue = df[mask].index.tolist()
    rescued = 0

    for idx in to_rescue:
        street = str(df.at[idx, "רחוב_ראשי"]).strip() if pd.notna(df.at[idx, "רחוב_ראשי"]) else ""

        if not street or street == "nan":
            continue

        if street in STREET_COORDS:
            lat, lon = STREET_COORDS[street]
            df.at[idx, "קו_רוחב"] = lat
            df.at[idx, "קו_אורך"] = lon
            df.at[idx, "geocode_method"] = "osm_centroid"
            df.at[idx, PRECISION_COL] = "street"
            df.at[idx, "geocode_query"] = street
            rescued += 1

    log.info(f"OSM centroids: rescued {rescued} rows")
    return df


# ============================================================================
#  GIS PORTAL RESCUE — Playwright token + ArcGIS query
# ============================================================================

def _get_gis_token_playwright() -> Optional[str]:
    """
    Use Playwright to visit the GIS portal and retrieve the JWT cookie.
    Returns the token string or None if Playwright is unavailable / fails.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.info("Playwright not installed — skipping GIS rescue")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto(GIS_HOME_URL, wait_until="networkidle", timeout=30000)
            # Wait for the cookie to be set
            time.sleep(2)
            cookies = context.cookies()
            token = None
            for cookie in cookies:
                if cookie["name"] == "_hertzeliya":
                    token = cookie["value"]
                    break
            browser.close()

            if token:
                log.info(f"GIS token retrieved via Playwright: {token[:20]}…")
            else:
                log.warning("GIS portal loaded but _hertzeliya cookie not found")
            return token
    except Exception as e:
        log.warning(f"Playwright GIS token retrieval failed: {e}")
        return None


def _make_gis_session(token: str):
    """Create a requests session with the GIS JWT cookie."""
    if not HAS_REQUESTS:
        return None
    s = requests.Session()
    s.headers.update(GIS_HEADERS)
    s.cookies.set("_hertzeliya", token, domain="v5.gis-net.co.il")
    return s


def _query_gis(session, street_name: str) -> list:
    """Query the GIS portal for all buildings on a given street."""
    qs = urllib.parse.urlencode({
        "f": "json",
        "text": "%",
        "where": f"street_nam='{street_name}'",
        "returnGeometry": "true",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "guid": str(uuid.uuid4()),
    })
    url = f"{GIS_PROXY_BASE}?{GIS_ARCGIS_PATH}?{qs}"
    try:
        r = session.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning(f"GIS query failed for '{street_name}': {e}")
        return []

    if "error" in data or not data.get("features"):
        return []

    results = []
    for feat in data["features"]:
        geom = feat.get("geometry", {})
        attrs = feat.get("attributes", {})
        if geom.get("x") and geom.get("y"):
            results.append({
                "bldg_num":   str(attrs.get("BLDG_NUM", "")).strip(),
                "street_nam": str(attrs.get("street_nam", "")).strip(),
                "x_itm":      geom["x"],
                "y_itm":      geom["y"],
            })
    return results


def _fetch_gis_street_list(session) -> list:
    """Fetch all street names from the GIS for fuzzy matching."""
    url = (
        f"{GIS_PROXY_BASE}?{GIS_ARCGIS_PATH}?"
        "f=json&where=1%3D1&returnGeometry=false"
        "&outFields=street_nam&returnDistinctValues=true"
        "&orderByFields=street_nam&resultRecordCount=2000"
    )
    try:
        r = session.get(url, timeout=20)
        data = r.json()
        streets = sorted(set(
            f["attributes"]["street_nam"]
            for f in data.get("features", [])
            if f["attributes"].get("street_nam")
        ))
        log.info(f"GIS street list: {len(streets)} streets")
        return streets
    except Exception as e:
        log.warning(f"Failed to fetch GIS street list: {e}")
        return []


def _resolve_gis_street_name(raw: str, gis_streets: list) -> Optional[str]:
    """Resolve a CRM street name to the GIS canonical name."""
    raw = raw.strip()

    # Pre-clean: strip suffixes that leaked into רחוב_ראשי from parse_address
    # e.g. "חנה רובינא -מתחם זרובבל" → "חנה רובינא"
    #      "רוזן פנחס 1 - כניסה" → "רוזן פנחס"
    cleaned = re.sub(r'\s*[-–]\s*(כניסה|קומה|דירה|מתחם|מגדל|בניין)\b.*$', '', raw).strip()
    # Strip trailing absorbed house number e.g. "רוזן פנחס 1" → "רוזן פנחס"
    cleaned = re.sub(r'\s+\d+\s*$', '', cleaned).strip()
    # Strip slash-separated secondary descriptor e.g. "מורי עפארי / גבעת האלוהים סימטה"
    if '/' in cleaned:
        cleaned = cleaned[:cleaned.index('/')].strip()

    # Combine GIS street list with registry names as fallback corpus.
    # When the GIS fetch returns empty (portal slow/down), registry provides coverage.
    fuzzy_corpus = list(gis_streets) if gis_streets else []
    if _REGISTRY_NAMES:
        fuzzy_corpus = fuzzy_corpus + [n for n in _REGISTRY_NAMES if n not in set(fuzzy_corpus)]

    def _lookup(name):
        if not name:
            return None
        # 1. Manual overrides (highest priority)
        if name in GIS_MANUAL_MAP:
            return GIS_MANUAL_MAP[name]
        # 2. Exact match in GIS streets
        if name in gis_streets:
            return name
        # 3. Registry resolve (word-set + fuzzy) — covers word-order reversals
        #    and CRM variants not yet in GIS_MANUAL_MAP
        reg_name, _ = _registry_resolve(name)
        if reg_name:
            # Prefer GIS-confirmed name; fall back to registry canonical
            if reg_name in gis_streets:
                return reg_name
            if reg_name != name:
                return reg_name
        # 4. Fuzzy match against combined corpus (GIS streets + registry)
        if HAS_DIFFLIB and fuzzy_corpus:
            matches = difflib.get_close_matches(name, fuzzy_corpus, n=1, cutoff=0.6)
            if matches:
                return matches[0]
        return None

    # 1. Try original raw
    result = _lookup(raw)
    if result is not None:
        return result

    # 2. Try cleaned (stripped suffixes)
    if cleaned != raw:
        result = _lookup(cleaned)
        if result is not None:
            return result

    # 3. Strip directional suffixes and retry
    for suffix in [' ליד ', ' מול ', ' עד ', ' בגינת ', ' שליד ', ' בחלק ']:
        if suffix in raw:
            stem = raw[:raw.index(suffix)].strip()
            result = _lookup(stem)
            if result is not None:
                return result

    return None


def _itm_to_wgs84(x, y):
    """Convert Israeli Transverse Mercator to WGS84."""
    if not HAS_PYPROJ:
        return None, None
    transformer = Transformer.from_crs("EPSG:2039", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(x, y)
    return round(lat, 7), round(lon, 7)


def _normalise_bldg_num(raw) -> Optional[str]:
    """Extract leading number from a building number string."""
    if pd.isna(raw):
        return None
    m = re.match(r"(\d+)", str(raw).strip())
    return m.group(1) if m else None


def gis_rescue_pass(df: pd.DataFrame,
                    progress_cb: Optional[Callable] = None,
                    checkpoint_cb: Optional[Callable] = None,
                    checkpoint_every: int = 100) -> pd.DataFrame:
    """
    For rows still missing coordinates, try the Herzliya GIS portal.
    Uses Playwright to auto-retrieve the JWT token.
    Gracefully skips if Playwright is not installed or portal is unreachable.
    """
    for col in ["קו_רוחב", "קו_אורך", "geocode_method", PRECISION_COL,
                "geocode_query"]:
        if col not in df.columns:
            df[col] = None

    mask = df["קו_רוחב"].isna() | (df["קו_רוחב"].astype(str).str.strip() == "")
    to_rescue = df[mask].index.tolist()

    if not to_rescue:
        log.info("GIS rescue: no rows to rescue")
        return df

    # Get token
    token = _get_gis_token_playwright()
    if not token:
        log.info("GIS rescue: no token — pass skipped")
        return df

    session = _make_gis_session(token)
    if not session:
        return df

    # Fetch GIS street list for fuzzy matching
    gis_streets = _fetch_gis_street_list(session)

    total = len(to_rescue)
    stats = {"exact": 0, "nearest": 0, "centroid": 0, "intersection": 0, "unresolved": 0}

    # Per-street cache for GIS queries
    gis_cache = {}

    for i, idx in enumerate(to_rescue):
        street = str(df.at[idx, "רחוב_ראשי"]).strip() if pd.notna(df.at[idx, "רחוב_ראשי"]) else ""
        bldg = df.at[idx, "מספר_בית"] if "מספר_בית" in df.columns else None

        if not street or street == "nan":
            df.at[idx, "geocode_method"] = df.at[idx, "geocode_method"] or "unresolved"
            stats["unresolved"] += 1
            continue

        # Resolve street name to GIS canonical
        gis_name = _resolve_gis_street_name(street, gis_streets)
        if gis_name is None:
            df.at[idx, "geocode_method"] = df.at[idx, "geocode_method"] or "unresolved"
            stats["unresolved"] += 1
            continue

        # Handle intersection
        if gis_name.startswith("__INTERSECTION__"):
            parts = gis_name.split("__")[2:]
            all_buildings = []
            for part in parts:
                if part in gis_cache:
                    all_buildings.extend(gis_cache[part])
                else:
                    time.sleep(GIS_DELAY)
                    buildings = _query_gis(session, part)
                    gis_cache[part] = buildings
                    all_buildings.extend(buildings)
            if not all_buildings:
                stats["unresolved"] += 1
                continue
            mx = sum(b["x_itm"] for b in all_buildings) / len(all_buildings)
            my = sum(b["y_itm"] for b in all_buildings) / len(all_buildings)
            lat, lon = _itm_to_wgs84(mx, my)
            if lat:
                df.at[idx, "קו_רוחב"] = lat
                df.at[idx, "קו_אורך"] = lon
                df.at[idx, "geocode_method"] = "gis_intersection"
                df.at[idx, PRECISION_COL] = "street"
                df.at[idx, "geocode_query"] = gis_name
                stats["intersection"] += 1
            continue

        # Query GIS (with cache)
        if gis_name in gis_cache:
            buildings = gis_cache[gis_name]
        else:
            time.sleep(GIS_DELAY)
            buildings = _query_gis(session, gis_name)
            gis_cache[gis_name] = buildings

        if not buildings:
            df.at[idx, "geocode_method"] = df.at[idx, "geocode_method"] or "unresolved"
            df.at[idx, PRECISION_COL] = "none"
            stats["unresolved"] += 1
            continue

        bldg_str = _normalise_bldg_num(bldg)
        is_street_level = (bldg_str is None or bldg_str == "0")

        if is_street_level:
            mx = sum(b["x_itm"] for b in buildings) / len(buildings)
            my = sum(b["y_itm"] for b in buildings) / len(buildings)
            lat, lon = _itm_to_wgs84(mx, my)
            if lat:
                df.at[idx, "קו_רוחב"] = lat
                df.at[idx, "קו_אורך"] = lon
                df.at[idx, "geocode_method"] = "gis_centroid"
                df.at[idx, PRECISION_COL] = "street"
                df.at[idx, "geocode_query"] = gis_name
                stats["centroid"] += 1
        else:
            exact = [b for b in buildings if b["bldg_num"] == bldg_str]
            if exact:
                lat, lon = _itm_to_wgs84(exact[0]["x_itm"], exact[0]["y_itm"])
                if lat:
                    df.at[idx, "קו_רוחב"] = lat
                    df.at[idx, "קו_אורך"] = lon
                    df.at[idx, "geocode_method"] = "gis_exact"
                    df.at[idx, PRECISION_COL] = "address"
                    df.at[idx, "geocode_query"] = gis_name
                    stats["exact"] += 1
            else:
                target = int(bldg_str)
                numbered = []
                for b in buildings:
                    m = re.match(r"(\d+)", b["bldg_num"])
                    if m:
                        numbered.append((abs(int(m.group(1)) - target), b))
                if numbered:
                    best = sorted(numbered, key=lambda t: t[0])[0][1]
                    lat, lon = _itm_to_wgs84(best["x_itm"], best["y_itm"])
                    if lat:
                        df.at[idx, "קו_רוחב"] = lat
                        df.at[idx, "קו_אורך"] = lon
                        df.at[idx, "geocode_method"] = "gis_nearest"
                        df.at[idx, PRECISION_COL] = "near_address"
                        df.at[idx, "geocode_query"] = gis_name
                        stats["nearest"] += 1
                else:
                    mx = sum(b["x_itm"] for b in buildings) / len(buildings)
                    my = sum(b["y_itm"] for b in buildings) / len(buildings)
                    lat, lon = _itm_to_wgs84(mx, my)
                    if lat:
                        df.at[idx, "קו_רוחב"] = lat
                        df.at[idx, "קו_אורך"] = lon
                        df.at[idx, "geocode_method"] = "gis_centroid"
                        df.at[idx, PRECISION_COL] = "street"
                        df.at[idx, "geocode_query"] = gis_name
                        stats["centroid"] += 1

        if progress_cb and (i + 1) % 10 == 0:
            progress_cb("gis", i + 1, total,
                         stats["exact"] + stats["nearest"] + stats["centroid"] + stats["intersection"],
                         stats["unresolved"])

        if checkpoint_cb and (i + 1) % checkpoint_every == 0:
            checkpoint_cb(df)

    log.info(f"GIS rescue: exact={stats['exact']}, nearest={stats['nearest']}, "
             f"centroid={stats['centroid']}, intersection={stats['intersection']}, "
             f"unresolved={stats['unresolved']}")

    if progress_cb:
        progress_cb("gis", total, total,
                     stats["exact"] + stats["nearest"] + stats["centroid"] + stats["intersection"],
                     stats["unresolved"])

    return df


# ============================================================================
#  MAIN ENTRY POINT
# ============================================================================

def geocode_dataframe(df: pd.DataFrame,
                      progress_cb: Optional[Callable] = None,
                      skip_nominatim: bool = False,
                      skip_gis: bool = False,
                      checkpoint_cb: Optional[Callable] = None,
                      checkpoint_every: int = 100) -> tuple:
    """
    Run the full geocoding pipeline on a cleaned DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Cleaned data (output of clean_pipeline). Must have רחוב_ראשי, מספר_בית,
        סוג_מיקום, רחוב_משני columns.
    progress_cb : callable, optional
        Called with (pass_name, current, total, geocoded, failed).
    skip_nominatim : bool
        If True, skip the Nominatim pass (for testing or if data already geocoded).
    skip_gis : bool
        If True, skip the GIS rescue pass.

    Returns
    -------
    (df, stats) : tuple
        df with added קו_רוחב, קו_אורך, geocode_method columns.
        stats dict with counts per method.
    """
    # Ensure columns exist
    for col in ["קו_רוחב", "קו_אורך", "geocode_method", PRECISION_COL, "geocode_query"]:
        if col not in df.columns:
            df[col] = None

    run_id = str(uuid.uuid4())
    df["geocode_run_id"] = run_id

    # Pass 1: Nominatim
    if not skip_nominatim:
        if progress_cb:
            progress_cb("status", 0, 0, 0, 0)
        df = nominatim_pass(df, progress_cb,
                            checkpoint_cb=checkpoint_cb,
                            checkpoint_every=checkpoint_every)

    # Pass 2: OSM centroids (always runs, it's offline and instant)
    df = osm_centroid_pass(df)

    # Pass 3: GIS rescue
    if not skip_gis:
        df = gis_rescue_pass(df, progress_cb,
                             checkpoint_cb=checkpoint_cb,
                             checkpoint_every=checkpoint_every)

    # Mark remaining unresolved
    still_missing = df["קו_רוחב"].isna() | (df["קו_רוחב"].astype(str).str.strip() == "")
    unresolved_mask = still_missing & df["geocode_method"].isna()
    df.loc[unresolved_mask, "geocode_method"] = "unresolved"
    df.loc[unresolved_mask, PRECISION_COL] = "none"

    # Attach official street code from municipal registry (best-effort, silent on miss)
    if STREET_REGISTRY and "רחוב_ראשי" in df.columns:
        def _lookup_code(street):
            if not street or str(street).strip() in ("", "nan", "None"):
                return None
            _, code = _registry_resolve(str(street).strip())
            return code if code else None
        df["קוד_רחוב"] = df["רחוב_ראשי"].apply(_lookup_code)
        matched = df["קוד_רחוב"].notna().sum()
        log.info(f"Street registry: matched {matched}/{len(df)} rows to street codes")

    # Build stats
    method_counts = df["geocode_method"].value_counts().to_dict()
    total_rows = len(df)
    total_geocoded = int((~still_missing).sum())
    total_unresolved = int(still_missing.sum())

    stats = {
        "total_rows":       total_rows,
        "total_geocoded":   total_geocoded,
        "total_unresolved": total_unresolved,
        "coverage_pct":     round(total_geocoded / total_rows * 100, 1) if total_rows else 0,
        "method_counts":    method_counts,
        "pipeline_version": PIPELINE_VERSION,
        "geocode_run_id":   run_id,
    }

    log.info(f"Geocoding complete: {total_geocoded}/{total_rows} "
             f"({stats['coverage_pct']}%) — {total_unresolved} unresolved")

    return df, stats


# ============================================================================
#  STANDALONE CLI
# ============================================================================

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) < 2:
        print("Usage: python geocode_pipeline.py input.xlsx [output.xlsx]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace(".xlsx", "_geocoded.xlsx")

    def cli_progress(pass_name, current, total, geocoded, failed):
        if total > 0:
            pct = current / total * 100
            print(f"  [{pass_name}] {current}/{total} ({pct:.0f}%) — geocoded: {geocoded}, failed: {failed}")

    print(f"Loading {input_file}...")
    df = pd.read_excel(input_file)
    print(f"  {len(df):,} rows loaded")

    df, stats = geocode_dataframe(df, progress_cb=cli_progress)

    print(f"\n{'='*50}")
    print(f"RESULTS")
    print(f"{'='*50}")
    print(f"  Total rows:      {stats['total_rows']:,}")
    print(f"  Geocoded:        {stats['total_geocoded']:,} ({stats['coverage_pct']}%)")
    print(f"  Unresolved:      {stats['total_unresolved']:,}")
    print(f"\n  By method:")
    for method, count in sorted(stats['method_counts'].items(), key=lambda x: -x[1]):
        print(f"    {method:25s} {count:,}")
    print(f"{'='*50}")

    df.to_excel(output_file, index=False)
    print(f"\nSaved to {output_file}")
