# Canonical-Dataset Policy

## Decision: Hybrid — keep v2 coordinates, re-derive downstream

The v2 enriched dataset (`geocoded_enriched_v2.xlsx`, 17,208 rows) embeds
hours of manual GIS work and three rounds of automated rescue passes.
Discarding its coordinates to re-geocode from scratch would be wasteful
and unreliable (Nominatim results are non-deterministic across runs).

### What the patch script does

1. **Keep** all v2 coordinate values as-is.
2. **Re-run enrichment** — zone assignment, collection-day, same-day flag —
   so rows fixed late get correct zones instead of "לא ידוע".
3. **Backfill `דיוק_גאוקוד`** (precision tier) using the rules below.
4. **Relabel provenance** — coordinate-bearing rows with method `unresolved`,
   `flagged_description`, or `no_street` are relabeled `manual_backfilled`.
5. **Coerce coordinates** to float64 (strip trailing commas, reject non-numeric).

### Precision tier backfill rules

| Condition | `דיוק_גאוקוד` |
|-----------|---------------|
| Coordinate pair shared by ≥5 rows spanning ≥4 distinct house numbers* | `street` |
| `nominatim_original` / `nominatim` / `nominatim_cached` (not collapsed) | `address_unverified` |
| `gis_exact` | `address` |
| `gis_nearest` | `near_address` |
| `gis_centroid` / `street_centroid_osm` / `gis_intersection` | `street` |
| `manual_backfilled` (formerly unresolved with coords) | `address` |
| No coordinates | `none` |

\* Exclusions from distinct-house-number count: NaN, "0", ranges
(`סוג_מיקום == "טווח בתים"`), and `ציון דרך` rows.

### Alternatives considered

| Approach | Pro | Con |
|----------|-----|-----|
| **Full regeneration** — re-geocode every row from the raw export | Single source of truth; every row gets a fresh precision label | Requires official GovMap/municipal API access (the Playwright token expires); Nominatim rate limits mean ~5 hours per run; results may differ from v2 |
| **Hybrid (chosen)** | Preserves manual work; patch runs in seconds; downstream enrichment is re-derived | Precision tier for `nominatim_original` rows is heuristic (collapsed-point detection), not ground-truth `place_rank` |

Full regeneration is deferred until official GovMap or municipal REST API
access replaces the Playwright-based token scraping.
