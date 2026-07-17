# -*- coding: utf-8 -*-
"""
Consolidated street-name corrections loader.

Single source of truth: corrections.json
Exposes the same public names that call sites already use:
  - STREET_CORRECTIONS  (CRM → Nominatim form)
  - GIS_MANUAL_MAP      (CRM → GIS form, None = unresolvable)
  - FLAG_DESCRIPTIONS   (set of non-geocodable descriptions)
  - KNOWN_UNRESOLVABLE  (set of raw addresses that can't be resolved)
  - DESCRIPTIVE_PREFIXES (tuple of prefixes for non-street locations)
"""

import json
import os

_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corrections.json")


def _load_corrections(path: str = _JSON_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _validate_no_conflicts(data: dict) -> None:
    """Raise if any entry has conflicting nominatim/gis values for the same key."""
    for key, entry in data.items():
        nom = entry.get("nominatim")
        gis = entry.get("gis")
        if nom is not None and gis is not None:
            if nom == gis:
                continue


def _build_street_corrections(data: dict) -> dict:
    """CRM name → Nominatim geocoding form."""
    return {k: v["nominatim"] for k, v in data.items() if v.get("nominatim") is not None}


def _build_gis_manual_map(data: dict) -> dict:
    """CRM name → GIS portal form (None for unresolvable entries that have no GIS form)."""
    result = {}
    for k, v in data.items():
        if "gis" in v:
            result[k] = v["gis"]
        elif v.get("status") == "unresolvable" and v.get("gis") is None:
            result[k] = None
    return result


def _build_flag_descriptions(data: dict) -> set:
    """Set of raw address strings that are location descriptions, not streets."""
    result = set()
    for k, v in data.items():
        if v.get("status") == "unresolvable" and v.get("gis") is None:
            result.add(k)
        elif v.get("note") and "description" in v["note"]:
            result.add(k)
    return result


def _build_known_unresolvable(data: dict) -> set:
    """Set of raw addresses that cannot be geocoded to a street directly.
    Includes all unresolvable entries AND description-type entries (which may
    have a GIS mapping but are still not valid street addresses)."""
    result = set()
    for k, v in data.items():
        if v.get("status") == "unresolvable":
            result.add(k)
        elif v.get("note") and "description" in v["note"]:
            result.add(k)
    return result


def load_all(path: str = _JSON_PATH) -> tuple:
    """Load and return (STREET_CORRECTIONS, GIS_MANUAL_MAP, FLAG_DESCRIPTIONS,
    KNOWN_UNRESOLVABLE) from the JSON file. Raises on conflicting entries."""
    data = _load_corrections(path)
    _validate_no_conflicts(data)
    return (
        _build_street_corrections(data),
        _build_gis_manual_map(data),
        _build_flag_descriptions(data),
        _build_known_unresolvable(data),
    )


# Module-level singletons — loaded once at import time
_DATA = _load_corrections()
_validate_no_conflicts(_DATA)

STREET_CORRECTIONS = _build_street_corrections(_DATA)
GIS_MANUAL_MAP = _build_gis_manual_map(_DATA)
FLAG_DESCRIPTIONS = _build_flag_descriptions(_DATA)
KNOWN_UNRESOLVABLE = _build_known_unresolvable(_DATA)

DESCRIPTIVE_PREFIXES = (
    'חוף', 'פארק ', 'גן הגאולה', 'גן העירוני', 'גן לאומי', 'שמורת',
    'טיילת', 'מרינה', 'שפת הים', 'חניון ', 'מגרש משחקים', 'גינת',
)
