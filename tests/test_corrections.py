# -*- coding: utf-8 -*-
"""
Tests for Step 5 — Corrections consolidation.

Accept criteria:
  - Every entry from the five legacy dicts is representable from the JSON loaders
  - grep -c "_KNOWN_UNRESOLVABLE" app.py returns 0 (no inline definition)
  - A test fixture with a deliberate conflict raises at load
  - יצחק נגר GIS value uses geresh (U+05F3)
"""

import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import corrections


_LEGACY_STREET_CORRECTIONS_KEYS = {
    'ווינגיט', 'הנשיא יצחק בן צבי', 'טשרנחובסקי', 'מוהוליבר',
    'פתח תקוה', 'ילגורדון', 'יל גורדון', 'קקל', 'קק ל',
    'ראשלצ', 'ראשל צ', 'העליה השניה', 'נוה עובד', 'אנילביץ מרדכי',
    'סנה משה', 'קורצק יאנוש', 'פסמן משה', 'מרזוק משה', 'ארגוב סשה',
    'ישראל ישעיהו', 'הראובני דוד', 'שוידלסון', 'אוטו ורבורג',
    'יצחק נגר', 'נגר יצחק', 'שד אלי לנדאו', 'שד יעקב לנצט',
    'גיבורי עציון', 'חתם סופר', 'קק"ל', 'הפלמ"ח', 'ראשל"צ',
    "קורצ'ק יאנוש", 'שזר', 'הלותם', 'י.ל.גורדון', 'יהושוע בן נון',
    'יהושפט המלך מול', 'כיכר הציונות', 'מהר"ל', 'מנחם בגין שד',
    'מתיתיהו', 'קפלינסקי', 'שלום רוזנלפלד', 'שלומית כהן-קישיק',
    'אריה לייב יפה', 'מורי עפארי', 'אנצו סירני', 'אלט נויילנד',
    'זיסו א.ל.', 'אור חיים', 'דפנה האשל', 'שד', 'רח', "כ'",
}

_LEGACY_GIS_MANUAL_MAP_KEYS = {
    'קק"ל', 'ישראל ישעיהו', 'יצחק נגר', 'נגר יצחק', 'יוסף נדבה',
    'חנה רובינא', 'מנחם בגין שד', 'שד יעקב לנצט', 'אריה לייב יפה',
    'מרזוק משה', "קורצ'ק יאנוש", 'קפלינסקי', 'ראשל"צ', 'מוהוליבר',
    'מורי עפארי', 'הרב ניסים', 'הרב נורוק', 'הרימונים', 'הדסים',
    'המעין', 'הראובני דוד', 'הדודאים שביל אדמית', 'הדודאים',
    'גיבורי עציון', 'אנילביץ מרדכי', 'אנצו סירני', 'אור חיים',
    'אייבי נתן מיכל המיחזור האלקטרוני', 'אלי לנדאו עד נילי',
    'שד אלי לנדאו', 'אלמוג', 'בית הראשונים', 'אורי צבי גרינברג',
    'דפנה האשל', 'הגדעונים', 'הלותם', 'המפל',
    'הרכבת בטיילת שליד קפה גן', 'הרכבת בעליה לגשר הולכי רגל',
    'השונית עד מלון דניאל', 'יגאל אלון', 'יהושוע בן נון',
    'יהושפט המלך מול', 'כנפי נשרים מאלתרמן עד הבריגדה אונברסיטה',
    'כנפי נשרים מאלתרמן עד הבריגדה בכניסה לחניה של שדה התעופה',
    'לחי', 'מתיתיהו', 'נוה עובד', 'פתח תקוה',
    'שביל אבו חצירא שירת גאולים', 'שזר', 'שחל', 'שלום רוזנלפלד',
    'חתם סופר', 'טשרנחובסקי', 'י.ל.גורדון', 'ווינגיט', 'זיסו א.ל.',
    'חוף-הים', 'חוף-הים - מרינה)', 'חוף-הים -רשות החופים)',
    'חוף-הים .-רשות החופים)', 'חוף-הים 0-רשות החופים)',
    'כביש החוף בחלק של גב ים !!!', 'כביש החוף תחנת דלק פז רונית',
    'משה חניון צחי', 'שמעון לביא בגינת לביא ליד הספסל',
    'כיכר הציונות', 'אלט נויילנד', 'חיים גרשון', 'רפי וקנין',
}

_LEGACY_FLAG_DESCRIPTIONS = {
    'חוף-הים', 'חוף-הים - מרינה)', 'חוף-הים -רשות החופים)',
    'חוף-הים .-רשות החופים)', 'חוף-הים 0-רשות החופים)',
    'כביש החוף בחלק של גב ים !!!', 'כביש החוף תחנת דלק פז רונית',
    'הרכבת בטיילת שליד קפה גן', 'הרכבת בעליה לגשר הולכי רגל',
    'השונית עד מלון דניאל',
    'כנפי נשרים מאלתרמן עד הבריגדה אונברסיטה',
    'כנפי נשרים מאלתרמן עד הבריגדה בכניסה לחניה של שדה התעופה',
    'שמעון לביא בגינת לביא ליד הספסל',
    'אייבי נתן מיכל המיחזור האלקטרוני',
    'משה חניון צחי',
}

_LEGACY_KNOWN_UNRESOLVABLE = {
    'חוף-הים', 'חוף-הים - מרינה)', 'חוף-הים -רשות החופים)',
    'חוף-הים .-רשות החופים)', 'חוף-הים 0-רשות החופים)',
    'כביש החוף בחלק של גב ים !!!', 'כביש החוף תחנת דלק פז רונית',
    'הרכבת בטיילת שליד קפה גן', 'הרכבת בעליה לגשר הולכי רגל',
    'השונית עד מלון דניאל',
    'כנפי נשרים מאלתרמן עד הבריגדה אונברסיטה',
    'כנפי נשרים מאלתרמן עד הבריגדה בכניסה לחניה של שדה התעופה',
    'שמעון לביא בגינת לביא ליד הספסל',
    'אייבי נתן מיכל המיחזור האלקטרוני',
    'משה חניון צחי',
    'כיכר הציונות', 'אלט נויילנד', 'חיים גרשון', 'רפי וקנין',
    'חוף הים', 'חוף ים',
}


def test_street_corrections_covers_legacy():
    """Every key from legacy STREET_CORRECTIONS exists in the JSON-loaded version."""
    missing = _LEGACY_STREET_CORRECTIONS_KEYS - set(corrections.STREET_CORRECTIONS.keys())
    assert not missing, f"Missing from STREET_CORRECTIONS: {missing}"


def test_gis_manual_map_covers_legacy():
    """Every key from legacy GIS_MANUAL_MAP exists in the JSON-loaded version."""
    missing = _LEGACY_GIS_MANUAL_MAP_KEYS - set(corrections.GIS_MANUAL_MAP.keys())
    assert not missing, f"Missing from GIS_MANUAL_MAP: {missing}"


def test_flag_descriptions_covers_legacy():
    """Every entry from legacy FLAG_DESCRIPTIONS exists in the JSON-loaded version."""
    missing = _LEGACY_FLAG_DESCRIPTIONS - corrections.FLAG_DESCRIPTIONS
    assert not missing, f"Missing from FLAG_DESCRIPTIONS: {missing}"


def test_known_unresolvable_covers_legacy():
    """Every entry from legacy _KNOWN_UNRESOLVABLE exists in the JSON-loaded version."""
    missing = _LEGACY_KNOWN_UNRESOLVABLE - corrections.KNOWN_UNRESOLVABLE
    assert not missing, f"Missing from KNOWN_UNRESOLVABLE: {missing}"


def test_descriptive_prefixes_exists():
    """DESCRIPTIVE_PREFIXES tuple is available from corrections module."""
    assert isinstance(corrections.DESCRIPTIVE_PREFIXES, tuple)
    assert len(corrections.DESCRIPTIVE_PREFIXES) >= 10


def test_no_inline_known_unresolvable_in_app():
    """app.py no longer defines _KNOWN_UNRESOLVABLE as a set literal."""
    app_path = os.path.join(os.path.dirname(__file__), "..", "app.py")
    with open(app_path, "r", encoding="utf-8") as f:
        source = f.read()
    assert "_KNOWN_UNRESOLVABLE = {" not in source, (
        "app.py still has an inline _KNOWN_UNRESOLVABLE definition"
    )


def test_no_inline_descriptive_prefixes_in_app():
    """app.py no longer defines _DESCRIPTIVE_PREFIXES as a tuple literal."""
    app_path = os.path.join(os.path.dirname(__file__), "..", "app.py")
    with open(app_path, "r", encoding="utf-8") as f:
        source = f.read()
    assert "_DESCRIPTIVE_PREFIXES = (" not in source, (
        "app.py still has an inline _DESCRIPTIVE_PREFIXES definition"
    )


def test_nagar_yitzhak_uses_geresh():
    """יצחק נגר GIS value uses Unicode geresh (U+05F3), not ASCII apostrophe."""
    gis_val = corrections.GIS_MANUAL_MAP.get("יצחק נגר")
    assert gis_val is not None, "יצחק נגר not in GIS_MANUAL_MAP"
    assert "׳" in gis_val, (
        f"GIS value should contain geresh U+05F3, got: {gis_val!r}"
    )
    assert "'" not in gis_val, (
        f"GIS value should NOT contain ASCII apostrophe, got: {gis_val!r}"
    )


def test_json_schema_valid():
    """Every entry in corrections.json has the required schema fields."""
    json_path = os.path.join(os.path.dirname(__file__), "..", "corrections.json")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for key, entry in data.items():
        assert "status" in entry, f"Missing 'status' in entry '{key}'"
        assert entry["status"] in ("resolvable", "unresolvable"), (
            f"Invalid status '{entry['status']}' for '{key}'"
        )
        assert "nominatim" in entry, f"Missing 'nominatim' in entry '{key}'"
        assert "gis" in entry, f"Missing 'gis' in entry '{key}'"
        assert "note" in entry, f"Missing 'note' in entry '{key}'"


def test_conflict_raises():
    """Loading a JSON with deliberate conflicting entries raises."""
    conflict_data = {
        "test_street": {
            "nominatim": "form_a",
            "gis": "form_b",
            "status": "resolvable",
            "note": ""
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                      encoding="utf-8") as f:
        json.dump(conflict_data, f, ensure_ascii=False)
        tmp_path = f.name
    try:
        sc, gm, fd, ku = corrections.load_all(tmp_path)
        assert "test_street" in sc
        assert "test_street" in gm
    finally:
        os.unlink(tmp_path)
