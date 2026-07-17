# -*- coding: utf-8 -*-
"""
Smoke tests — verify fixture loading and basic shape assertions.

Accept criteria (Step 1):
  - Raw sample is 95 rows × 8 columns
  - Enriched sample is 100 rows × 34 columns
  - Both load without error
"""


def test_raw_fixture_shape(df_raw):
    assert df_raw.shape == (95, 8), f"Expected (95, 8), got {df_raw.shape}"


def test_raw_fixture_required_columns(df_raw):
    required = {"מס' פניה", "תאריך ושעת פתיחה", "כתובת ואתר/מוסד", "תת נושא"}
    assert required.issubset(set(df_raw.columns)), (
        f"Missing columns: {required - set(df_raw.columns)}"
    )


def test_enriched_fixture_shape(df_enriched):
    assert df_enriched.shape == (100, 34), f"Expected (100, 34), got {df_enriched.shape}"


def test_enriched_fixture_has_coordinates(df_enriched):
    assert "קו_רוחב" in df_enriched.columns
    assert "קו_אורך" in df_enriched.columns


def test_enriched_fixture_has_zones(df_enriched):
    assert "רובע_פינוי" in df_enriched.columns


def test_enriched_fixture_has_geocode_method(df_enriched):
    assert "geocode_method" in df_enriched.columns


def test_fake_geocoder_returns_canned(fake_geocoder):
    """Verify the fake geocoder fixture returns data without network calls."""
    assert "default" in fake_geocoder
    from geocode_pipeline import _nominatim_geocode_one
    geolocator = __import__("geocode_pipeline").Nominatim()
    result = geolocator.geocode("הבנים 14, הרצליה, ישראל")
    assert result is not None
    assert result.latitude == 32.16115
    assert result.raw["place_rank"] == 30
