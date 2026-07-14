import sys
sys.path.insert(0, '.')
from geocode_pipeline import (
    _get_gis_token_playwright, _make_gis_session,
    _fetch_gis_street_list, _query_gis, _resolve_gis_street_name,
    GIS_MANUAL_MAP
)

print("Getting GIS token...")
token = _get_gis_token_playwright()
if not token:
    print("FAILED: no token retrieved")
    sys.exit(1)
print(f"Token OK: {token[:20]}...")

session = _make_gis_session(token)

print("\nFetching street list...")
streets = _fetch_gis_street_list(session)
print(f"Got {len(streets)} streets")

# Streets from the failing rows
crm_names = [
    'הרב ניסים', 'אורי צבי גרינברג', 'שזר', 'המעלות',
    'קק"ל', 'הפלמ"ח', 'מהר"ל', 'ראשל"צ',
    'יצחק נגר', 'פסמן משה', 'ישראל ישעיהו',
    'חנה רובינא', 'אלמוג', 'אביב גל', 'יוסף נדבה',
]

print("\n--- Street name resolution ---")
for name in crm_names:
    resolved = _resolve_gis_street_name(name, streets)
    print(f"  {name!r:30s} -> {resolved!r}")

print("\n--- GIS queries for resolved names ---")
for name in crm_names:
    resolved = _resolve_gis_street_name(name, streets)
    if resolved and not resolved.startswith('__'):
        buildings = _query_gis(session, resolved)
        print(f"  {resolved!r:30s} -> {len(buildings)} buildings")
    else:
        print(f"  {name!r:30s} -> could not resolve")
