# Council PDF Ingestion Runbook

## Goal

Build a metro-wide Perth bike-path overlay from council map PDFs, then use it as a first-class routing preference signal.

## Pipeline

1. `python3 scripts/06_download_council_maps.py`
2. `python3 scripts/07_extract_council_map_network.py`
3. `python3 scripts/03_build_graph.py`
4. `python3 scripts/04_classify_edges.py`
5. `python3 scripts/05_export_router_data.py`

## Data taxonomy and confidence

Extracted PDF features are tagged as:

- `psp` (strong dedicated corridor signal)
- `shared_path`
- `bike_lane`
- `quiet_street`
- `unknown`

Confidence (`0.0`-`1.0`) is inferred from stroke style heuristics:

- colour dominance (green/blue families)
- stroke width
- segment continuity and metric length

## Precedence and conflation rules

Classification precedence:

1. `council_pdf:<council>`
2. `mrwa_psp_nodes`
3. `ltcn_primary`
4. OSM-only defaults

Edge conflation thresholds:

- PSP/shared-path overlays with `confidence >= 0.55` can promote edges to `PSP`.
- Bike-lane overlays with `confidence >= 0.45` can promote `BUSY_ROAD_NO_INFRA` to `CYCLE_LANE_PAINTED`.
- Spatial match buffer: `12m`.

## QA and rollout

Use incremental rollout by enabling one council map at a time in `config/data_sources.json`.

Validation loop per rollout batch:

1. Confirm extraction counts in `data/council_maps/processed/extraction_manifest.json`.
2. Inspect `data/export/council_overlay.geojson` in QGIS.
3. Run route regression:
   - `cd ../api`
   - `python3 scripts/route_regression.py --api-url http://127.0.0.1:8000`
4. Track `psp_share` and `busy_road_m` deltas before/after the council batch.

## Known constraints

- Non-georeferenced PDFs use a council-level `fallback_bbox` transform and therefore need larger conflation buffers and manual QA.
- Style-based taxonomy is heuristic and should be calibrated with per-council legend sampling.
- Some older map editions have lower cartographic consistency and may need council-specific thresholds.
