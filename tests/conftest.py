# -*- coding: utf-8 -*-
"""
Shared pytest fixtures for the Herzliya sanitation-app test suite.

Provides:
  - df_raw          — 95-row raw CRM export sample (8 columns)
  - df_enriched     — 100-row enriched output sample (34 columns)
  - fake_geocoder   — monkeypatch fixture returning canned (lat, lon, place_rank)
  - tmp_xlsx        — helper to write a DataFrame to a temp .xlsx and return the path
"""

import os
import sys
import pytest
import pandas as pd

# Ensure the app package root is importable
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

_FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


@pytest.fixture
def df_raw() -> pd.DataFrame:
    """Load the 95-row raw CRM export fixture."""
    path = os.path.join(_FIXTURES_DIR, "sample_raw_export.xlsx")
    return pd.read_excel(path)


@pytest.fixture
def df_enriched() -> pd.DataFrame:
    """Load the 100-row enriched output fixture."""
    path = os.path.join(_FIXTURES_DIR, "sample_enriched_output.xlsx")
    return pd.read_excel(path)


# ── Canned geocode responses ─────────────────────────────────────────────────

_CANNED_RESPONSES = {
    "הבנים, הרצליה, ישראל":              (32.16110, 34.84530, 26),
    "הבנים 14, הרצליה, ישראל":           (32.16115, 34.84535, 30),
    "סוקולוב 50, הרצליה, ישראל":         (32.16280, 34.84450, 30),
    "סוקולוב, הרצליה, ישראל":            (32.16260, 34.84420, 26),
    "בן גוריון 1, הרצליה, ישראל":        (32.16350, 34.84110, 30),
    "ויצמן 10, הרצליה, ישראל":           (32.16190, 34.84280, 30),
    "הרצל 5, הרצליה, ישראל":             (32.16400, 34.84600, 30),
    "ירושלים 20, הרצליה, ישראל":          (32.16500, 34.84700, 30),
    "ז'בוטינסקי 30, הרצליה, ישראל":      (32.16600, 34.84800, 30),
    "default":                            (32.16600, 34.84200, 26),
}


class _FakeGeocodeResult:
    """Mimics geopy Location with .latitude, .longitude, .raw."""

    def __init__(self, lat, lon, place_rank):
        self.latitude = lat
        self.longitude = lon
        self.raw = {
            "place_id": 12345,
            "place_rank": place_rank,
            "addresstype": "building" if place_rank == 30 else "road",
            "display_name": "fake",
        }


class FakeGeolocator:
    """Drop-in replacement for geopy.geocoders.Nominatim — never hits the network."""

    def __init__(self, **kwargs):
        pass

    def geocode(self, query, **kwargs):
        q = query.strip()
        if q in _CANNED_RESPONSES:
            lat, lon, rank = _CANNED_RESPONSES[q]
        else:
            lat, lon, rank = _CANNED_RESPONSES["default"]
        return _FakeGeocodeResult(lat, lon, rank)


@pytest.fixture
def fake_geocoder(monkeypatch):
    """
    Monkeypatch geopy.geocoders.Nominatim so no test ever hits the network.
    Returns canned (lat, lon, place_rank) per query string.
    Also patches time.sleep to make tests fast.
    """
    import geocode_pipeline as gp

    monkeypatch.setattr(gp, "HAS_GEOPY", True)

    # Patch Nominatim constructor in geocode_pipeline
    monkeypatch.setattr("geocode_pipeline.Nominatim", FakeGeolocator)

    # Kill network delays
    import time as _time
    monkeypatch.setattr(_time, "sleep", lambda _: None)

    # Disable GIS rescue (needs Playwright)
    monkeypatch.setattr(gp, "_get_gis_token_playwright", lambda: None)

    return _CANNED_RESPONSES


@pytest.fixture
def tmp_xlsx(tmp_path):
    """Helper: write a DataFrame to a temp .xlsx and return the path."""
    def _write(df: pd.DataFrame, name: str = "test.xlsx") -> str:
        p = os.path.join(str(tmp_path), name)
        df.to_excel(p, index=False)
        return p
    return _write
