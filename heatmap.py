# -*- coding: utf-8 -*-
# ============================================================================
#  heatmap.py
#  עיריית הרצליה — מפת חום מוטמעת (Leaflet)
#  Herzliya Municipality — Inline Heatmap Builder
# ============================================================================
#
#  build_heatmap(df, ...) -> HTML string
#  The Streamlit app filters the data; this module only visualises whatever
#  rows it's handed. Embed the result with st.components.v1.html(html, height=...).
#
#  Requires columns: קו_רוחב (lat), קו_אורך (lon).
#  Optional: תת_נושא_חדש (category, for popups), רובע_פינוי (zone).
# ============================================================================

import json
import pandas as pd

HERZLIYA_CENTER = (32.1660, 34.8250)


def _points_payload(df: pd.DataFrame, weight_col: str = None) -> list:
    """Build a compact [[lat, lon, weight], ...] payload for Leaflet.heat."""
    lat = pd.to_numeric(df["קו_רוחב"].astype(str).str.replace(",", ""), errors="coerce")
    lon = pd.to_numeric(df["קו_אורך"].astype(str).str.replace(",", ""), errors="coerce")
    ok = lat.notna() & lon.notna()

    if weight_col and weight_col in df.columns:
        w = pd.to_numeric(df[weight_col], errors="coerce").fillna(1.0)
    else:
        w = pd.Series([1.0] * len(df), index=df.index)

    pts = []
    for la, lo, ww in zip(lat[ok], lon[ok], w[ok]):
        pts.append([round(float(la), 6), round(float(lo), 6), float(ww)])
    return pts


def _marker_payload(df: pd.DataFrame, max_markers: int = 3000) -> list:
    """Build marker data with popup text (capped for performance)."""
    lat = pd.to_numeric(df["קו_רוחב"].astype(str).str.replace(",", ""), errors="coerce")
    lon = pd.to_numeric(df["קו_אורך"].astype(str).str.replace(",", ""), errors="coerce")
    ok = lat.notna() & lon.notna()
    sub = df[ok].head(max_markers)
    lat, lon = lat[ok].head(max_markers), lon[ok].head(max_markers)

    def _g(row, col):
        v = row.get(col, "")
        return "" if pd.isna(v) else str(v)

    markers = []
    for (_, row), la, lo in zip(sub.iterrows(), lat, lon):
        popup = "<br>".join(filter(None, [
            f"<b>{_g(row, 'רחוב_ראשי')} {_g(row, 'מספר_בית')}</b>",
            _g(row, "תת_נושא_חדש"),
            _g(row, "רובע_פינוי"),
            _g(row, "תאריך"),
        ]))
        markers.append([round(float(la), 6), round(float(lo), 6), popup])
    return markers


def build_heatmap(df: pd.DataFrame,
                  weight_col: str = None,
                  show_markers: bool = True,
                  radius: int = 18,
                  blur: int = 22,
                  title: str = "") -> str:
    """
    Return a self-contained Leaflet HTML document (string) rendering a heatmap
    of the rows in df. Embed with st.components.v1.html(html, height=600).
    """
    points = _points_payload(df, weight_col)
    markers = _marker_payload(df) if show_markers else []

    points_json = json.dumps(points)
    markers_json = json.dumps(markers, ensure_ascii=False)
    center_json = json.dumps(HERZLIYA_CENTER)

    n_points = len(points)
    title_html = f'<div class="map-title">{title}</div>' if title else ""

    return f"""<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css" />
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css" />
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ height:100%; font-family:'Heebo',Arial,sans-serif; }}
  #map {{ height:100%; width:100%; border-radius:10px; }}
  .map-title {{
    position:absolute; top:12px; right:12px; z-index:1000;
    background:rgba(26,58,92,0.92); color:#fff; padding:8px 14px;
    border-radius:8px; font-size:14px; font-weight:600; direction:rtl;
    box-shadow:0 2px 8px rgba(0,0,0,0.2);
  }}
  .map-controls {{
    position:absolute; bottom:22px; right:12px; z-index:1000;
    background:rgba(255,255,255,0.96); padding:10px 12px; border-radius:8px;
    direction:rtl; font-size:12px; box-shadow:0 2px 8px rgba(0,0,0,0.15);
    min-width:180px;
  }}
  .map-controls .row {{ display:flex; align-items:center; gap:8px; margin:5px 0; }}
  .map-controls label {{ min-width:52px; color:#334155; }}
  .map-controls input[type=range] {{ flex:1; accent-color:#2563a8; }}
  .map-controls .val {{ min-width:26px; text-align:center; color:#2563a8; font-weight:600; }}
  .map-controls .layer-row {{ display:flex; gap:6px; margin-bottom:6px; }}
  .map-controls .layer-btn {{
    flex:1; padding:4px 6px; border:1px solid #cbd5e1; border-radius:5px;
    background:#f8fafc; color:#475569; cursor:pointer; font-size:11px; text-align:center;
  }}
  .map-controls .layer-btn.active {{ background:#2563a8; color:#fff; border-color:#2563a8; }}
  .map-count {{
    position:absolute; bottom:22px; left:12px; z-index:1000;
    background:rgba(255,255,255,0.96); padding:8px 12px; border-radius:8px;
    direction:rtl; font-size:12px; box-shadow:0 2px 8px rgba(0,0,0,0.15); color:#1a3a5c;
  }}
  .map-count b {{ font-size:16px; color:#2563a8; }}
</style>
</head>
<body>
<div id="map"></div>
{title_html}
<div class="map-count">נקודות במפה: <b>{n_points:,}</b></div>
<div class="map-controls">
  <div class="layer-row">
    <div class="layer-btn active" id="btn-heat" onclick="setLayer('heat')">מפת חום</div>
    <div class="layer-btn" id="btn-markers" onclick="setLayer('markers')">סמנים</div>
  </div>
  <div class="row">
    <label>רדיוס</label>
    <input type="range" id="radius" min="5" max="45" value="{radius}" oninput="updateHeat()">
    <span class="val" id="radius-val">{radius}</span>
  </div>
  <div class="row">
    <label>טשטוש</label>
    <input type="range" id="blur" min="5" max="45" value="{blur}" oninput="updateHeat()">
    <span class="val" id="blur-val">{blur}</span>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script>
  const CENTER = {center_json};
  const POINTS = {points_json};
  const MARKERS = {markers_json};

  const map = L.map('map', {{ zoomControl:true }}).setView(CENTER, 13);
  L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    attribution:'&copy; OpenStreetMap &copy; CARTO', maxZoom:19
  }}).addTo(map);

  let heatLayer = null;
  let clusterLayer = null;
  let currentLayer = 'heat';

  function buildHeat() {{
    const r = parseInt(document.getElementById('radius').value);
    const b = parseInt(document.getElementById('blur').value);
    if (heatLayer) map.removeLayer(heatLayer);
    heatLayer = L.heatLayer(POINTS, {{
      radius:r, blur:b, maxZoom:17,
      gradient:{{0.2:'#2563a8',0.4:'#059669',0.6:'#d97706',0.8:'#dc2626',1.0:'#7c1d1d'}}
    }});
    if (currentLayer === 'heat') heatLayer.addTo(map);
  }}

  function buildClusters() {{
    if (clusterLayer) map.removeLayer(clusterLayer);
    clusterLayer = L.markerClusterGroup({{ chunkedLoading:true, maxClusterRadius:50 }});
    MARKERS.forEach(m => {{
      const marker = L.circleMarker([m[0], m[1]], {{
        radius:5, color:'#2563a8', fillColor:'#2563a8', fillOpacity:0.7, weight:1
      }});
      if (m[2]) marker.bindPopup(m[2]);
      clusterLayer.addLayer(marker);
    }});
    if (currentLayer === 'markers') clusterLayer.addTo(map);
  }}

  function updateHeat() {{
    document.getElementById('radius-val').textContent = document.getElementById('radius').value;
    document.getElementById('blur-val').textContent = document.getElementById('blur').value;
    buildHeat();
  }}

  function setLayer(which) {{
    currentLayer = which;
    document.getElementById('btn-heat').classList.toggle('active', which==='heat');
    document.getElementById('btn-markers').classList.toggle('active', which==='markers');
    if (which === 'heat') {{
      if (clusterLayer) map.removeLayer(clusterLayer);
      buildHeat();
    }} else {{
      if (heatLayer) map.removeLayer(heatLayer);
      if (!clusterLayer) buildClusters();
      else clusterLayer.addTo(map);
    }}
  }}

  buildHeat();
  if (POINTS.length > 0) {{
    const lats = POINTS.map(p => p[0]), lons = POINTS.map(p => p[1]);
    const bounds = [[Math.min(...lats), Math.min(...lons)], [Math.max(...lats), Math.max(...lons)]];
    try {{ map.fitBounds(bounds, {{ padding:[30,30], maxZoom:15 }}); }} catch(e) {{}}
  }}
</script>
</body>
</html>"""
