import sys
sys.path.insert(0, '.')
from geocode_pipeline import _get_gis_token_playwright, _make_gis_session, _fetch_gis_street_list, _query_gis, GIS_PROXY_BASE, GIS_ARCGIS_PATH, GIS_HEADERS
import urllib.parse, uuid, requests

token = _get_gis_token_playwright()
session = _make_gis_session(token)
streets = _fetch_gis_street_list(session)

# Find the exact string in the GIS street list
nagr_matches = [s for s in streets if 'נג' in s]
print("Streets containing נג:", nagr_matches)

for s in nagr_matches:
    print(f"  {s!r} bytes: {s.encode('utf-8').hex()}")

# Try querying each variant
for name in nagr_matches:
    buildings = _query_gis(session, name)
    print(f"  Query '{name}' -> {len(buildings)} buildings")

# Also try the raw street name as it appears in the list
target = 'נג\u05f3ר יצחק'  # geresh
print(f"\nTarget: {target!r} = {target.encode('utf-8').hex()}")
print(f"In streets: {target in streets}")

# Try manually building the query URL to see what's happening
qs = urllib.parse.urlencode({
    "f": "json",
    "text": "%",
    "where": f"street_nam='{target}'",
    "returnGeometry": "true",
    "spatialRel": "esriSpatialRelIntersects",
    "outFields": "*",
    "guid": str(uuid.uuid4()),
})
url = f"{GIS_PROXY_BASE}?{GIS_ARCGIS_PATH}?{qs}"
print(f"\nQuery URL (first 200 chars): {url[:200]}")
r = session.get(url, timeout=15)
data = r.json()
print(f"Response: error={data.get('error')}, features={len(data.get('features', []))}")
if data.get('error'):
    print(f"Error detail: {data['error']}")
