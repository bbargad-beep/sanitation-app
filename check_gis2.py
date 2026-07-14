import sys
sys.path.insert(0, '.')
from geocode_pipeline import _get_gis_token_playwright, _make_gis_session, _fetch_gis_street_list, _query_gis
import difflib

token = _get_gis_token_playwright()
session = _make_gis_session(token)
streets = _fetch_gis_street_list(session)

# Print all streets containing these substrings
searches = ['גרינברג', 'נגר', 'רובינא', 'פלמח', 'מהר', 'אורי', 'גל', 'מעלות', 'דודאים', 'שזר', 'פסמן', 'המעלות']
for s in searches:
    matches = [st for st in streets if s in st]
    if matches:
        print(f"\n'{s}': {matches}")

print("\n\nFull street list:")
for st in sorted(streets):
    print(f"  {st}")
