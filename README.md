# Perth-PSP-Priority

## Local rebuild and run

### 1) Build WA + council-enriched routing artefacts

Run ETL through council PDF extraction, classification, and export so these files are produced:

- `data/export/psp_way_priority.json` (WA-informed `osm_way_id` ranking map)
- `data/export/areas/graphhopper_custom_areas.geojson` (WA-informed corridor areas)
- `data/export/council_overlay.geojson` (PDF-derived council overlay for QA)

Example:

1. `cd etl`
2. `python3 -m venv .venv`
3. `source .venv/bin/activate`
4. `pip install -r requirements.txt`
5. Run ETL sequence:
   - `06_download_council_maps.py`
   - `07_extract_council_map_network.py`
   - `03_build_graph.py`
   - `04_classify_edges.py`
   - `05_export_router_data.py`

The council stage first attempts embedded GeoPDF georeferencing, then falls back to council `fallback_bbox` calibration when metadata is absent.

If ETL is not available, create the directory anyway so GraphHopper boots:

- `mkdir -p data/export`

### 2) Rebuild and launch GraphHopper

1. `rm -rf data/graph-cache && mkdir -p data/graph-cache`
2. `docker rm -f psp-graphhopper || true`
3. `docker run --name psp-graphhopper -p 8989:8989 -e JAVA_OPTS="-Xmx2g -Xms512m" -v "$PWD/graphhopper/config.yml:/graphhopper/config.yml" -v "$PWD/graphhopper/custom_models:/graphhopper/custom_models" -v "$PWD/data/osm:/graphhopper/data" -v "$PWD/data/export:/graphhopper/data/export" -v "$PWD/data/graph-cache:/graphhopper/graph-cache" israelhikingmap/graphhopper:latest -c config.yml`

### 3) Launch API + web client

1. `cd api`
2. `python3 -m venv .venv`
3. `source .venv/bin/activate`
4. `pip install -r requirements.txt`
5. `uvicorn app.main:app --host 127.0.0.1 --port 8000`
6. Open `http://127.0.0.1:8000`

## Behaviour notes

- Default detour tolerance is now `1.25` (up to 25% longer than shortest).
- Route selection is lexicographic within detour cap: maximise PSP share, then minimise busy-road distance, then minimise total distance.
- Routing supports `hard_psp_anchor` mode: approach a dedicated corridor safely, stay on dedicated infrastructure for the corridor phase, then egress safely.
- The web MVP now exposes quick presets (`Road-leaning`, `Balanced`, `PSP-max`) and a continuous `Bike-path weighting` slider (`0-100`).
- Hard mode now uses deterministic PSP anchoring: find nearest dedicated anchors for origin and destination, then route access/corridor/egress.
- The web MVP supports selecting:
  - a manual PSP via-point (`P`) to force corridor intent, and
  - preferred council overlays to guide deterministic anchor selection.
- The slider maps to API preferences (`psp_weight`, `psp_priority`) and is sent with `routing_mode=hard_psp_anchor`.
- If suitable anchors are not found for a route, the API returns `hard_anchor_unavailable` and falls back to weighted PSP routing.
- If GraphHopper is down, API still returns a direct fallback route for end-to-end UI testing.

## API additions for MVP

- `GET /v1/councils`: returns available council overlay names for UI selection.
- `POST /v1/route` now accepts:
  - `preferences.preferred_councils: list[str]`
  - `waypoints` for manual corridor shaping (used by the UI as PSP via-point).

## Validation workflow

1. Start GraphHopper and API using the steps above.
2. In the web UI, set origin and destination and choose a preset or slider value.
3. Click `Calculate route` and inspect:
   - `PSP share`,
   - on-road/busy-road exposure in API output,
   - warnings (`hard_anchor_unavailable` or `fallback_routing`).
4. For regression checks, compare `routing_mode=weighted` versus `routing_mode=hard_psp_anchor` on the same O/D pair.
5. Run API regression checks:
   - `cd api`
   - `python3 scripts/route_regression.py --api-url http://127.0.0.1:8000`
   - Includes a `kwinana_psp_corridor` must-pass case with warning gates.
6. See `docs/MVP_ACCEPTANCE.md` for deterministic pass/fail criteria.

## Council PDF data strategy

- Source priority is now: `council_pdf` > `MRWA` > `DoT LTCN` > OSM-only bike tags.
- `etl/scripts/07_extract_council_map_network.py` extracts vector lines from geospatial council maps and tags each segment with:
  - `path_class` (`psp`, `shared_path`, `bike_lane`, `quiet_street`, `unknown`)
  - `confidence` (0-1 extraction confidence)
  - provenance (`source_pdf`, `source_page`, `extract_version`, `council`)
- `04_classify_edges.py` conflates council-derived lines to network edges using spatial buffering and confidence thresholds.