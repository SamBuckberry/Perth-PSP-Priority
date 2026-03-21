"""Classify edges as PSP using WA government overlay data.

This script map-matches DoT LTCN Primary Routes and MRWA PSP nodes
to OSM edges in PostGIS, upgrading facility_class to PSP where appropriate.
"""

import json
import os
from pathlib import Path

import geopandas as gpd
from sqlalchemy import create_engine, text

DATA_DIR = os.environ.get("DATA_DIR", "/data")

DB_URL = (
    f"postgresql://{os.environ.get('POSTGRES_USER', 'psp')}:"
    f"{os.environ.get('POSTGRES_PASSWORD', 'psp_dev_password')}@"
    f"{os.environ.get('POSTGRES_HOST', 'localhost')}:"
    f"{os.environ.get('POSTGRES_PORT', '5432')}/"
    f"{os.environ.get('POSTGRES_DB', 'perth_psp')}"
)

# Buffer distance in metres for spatial matching (MGA Zone 50)
MATCH_BUFFER_M = 15


def load_ltcn_to_postgis(engine):
    """Load DoT LTCN shapefile into staging table."""
    ltcn_dir = os.path.join(DATA_DIR, "ltcn")
    if not os.path.isdir(ltcn_dir):
        print("WARNING: LTCN directory missing, skipping LTCN overlay")
        return

    # Find the shapefile
    shp_files = [f for f in os.listdir(ltcn_dir) if f.endswith(".shp")]
    if not shp_files:
        print("WARNING: No LTCN shapefile found, skipping LTCN overlay")
        return

    shp_path = os.path.join(ltcn_dir, shp_files[0])
    print(f"Loading LTCN shapefile: {shp_path}")

    gdf = gpd.read_file(shp_path)

    # Reproject from GDA2020 geographic (EPSG:7844) to MGA Zone 50 (EPSG:7850)
    if gdf.crs and gdf.crs.to_epsg() != 7850:
        gdf = gdf.to_crs("EPSG:7850")

    # Standardise column names
    col_map = {}
    for col in gdf.columns:
        lower = col.lower()
        if "hierarchy" in lower:
            col_map[col] = "hierarchy"
        elif "route_id" in lower or "routeid" in lower:
            col_map[col] = "route_id"
        elif "ltcn_name" in lower or "name" in lower:
            col_map[col] = "ltcn_name"
        elif "lga" in lower:
            col_map[col] = "lga_name"

    gdf = gdf.rename(columns=col_map)
    gdf = gdf.loc[:, ~gdf.columns.duplicated()]
    gdf = gdf.rename(columns={"geometry": "geom"})
    gdf = gdf.set_geometry("geom")

    gdf.to_postgis("ltcn_overlay", engine, if_exists="replace", index=False)
    print(f"Loaded {len(gdf)} LTCN features")


def load_mrwa_to_postgis(engine):
    """Load MRWA GeoJSON files into staging tables."""
    mrwa_dir = os.path.join(DATA_DIR, "mrwa")
    if not os.path.isdir(mrwa_dir):
        print("WARNING: MRWA directory missing, skipping MRWA overlay")
        return

    # Road network (controlled paths)
    road_path = os.path.join(mrwa_dir, "road_network.geojson")
    if os.path.exists(road_path):
        gdf = gpd.read_file(road_path)
        if len(gdf) > 0:
            if gdf.crs and gdf.crs.to_epsg() != 7850:
                gdf = gdf.to_crs("EPSG:7850")
            gdf = gdf.rename(columns={"geometry": "geom"}).set_geometry("geom")
            gdf.to_postgis("mrwa_road_asset", engine, if_exists="replace", index=False)
            print(f"Loaded {len(gdf)} MRWA road assets")

    # Intersections (PSP nodes)
    int_path = os.path.join(mrwa_dir, "intersections.geojson")
    if os.path.exists(int_path):
        gdf = gpd.read_file(int_path)
        if len(gdf) > 0:
            if gdf.crs and gdf.crs.to_epsg() != 7850:
                gdf = gdf.to_crs("EPSG:7850")
            gdf = gdf.rename(columns={"geometry": "geom"}).set_geometry("geom")
            gdf.to_postgis("mrwa_intersection", engine, if_exists="replace", index=False)
            print(f"Loaded {len(gdf)} MRWA PSP intersections")

    # Crash data
    crash_path = os.path.join(mrwa_dir, "crashes.geojson")
    if os.path.exists(crash_path):
        gdf = gpd.read_file(crash_path)
        if len(gdf) > 0:
            if gdf.crs and gdf.crs.to_epsg() != 7850:
                gdf = gdf.to_crs("EPSG:7850")
            gdf = gdf.rename(columns={"geometry": "geom"}).set_geometry("geom")
            gdf.to_postgis("mrwa_crash", engine, if_exists="replace", index=False)
            print(f"Loaded {len(gdf)} MRWA bike crashes")


def load_council_overlays_to_postgis(engine):
    """Load extracted council PDF overlays into staging table."""
    overlays_dir = Path(DATA_DIR) / "council_maps" / "processed"
    if not overlays_dir.exists():
        print("WARNING: council overlay directory missing, skipping council overlay load")
        return

    overlay_files = sorted(
        p for p in overlays_dir.glob("*_overlay.geojson") if p.name != "metro_council_overlay.geojson"
    )
    if not overlay_files:
        print("WARNING: no council overlay files found, skipping council overlay load")
        return

    frames = []
    for overlay_path in overlay_files:
        try:
            gdf = gpd.read_file(overlay_path)
        except Exception as exc:
            print(f"WARNING: could not read {overlay_path.name}: {exc}")
            continue
        if len(gdf) == 0:
            continue
        if gdf.crs and gdf.crs.to_epsg() != 7850:
            gdf = gdf.to_crs("EPSG:7850")
        if "confidence" not in gdf.columns:
            gdf["confidence"] = 0.4
        if "path_class" not in gdf.columns:
            gdf["path_class"] = "unknown"
        if "council" not in gdf.columns:
            gdf["council"] = overlay_path.stem.replace("_overlay", "")
        if "georef_mode" not in gdf.columns:
            gdf["georef_mode"] = "embedded"
        gdf = gdf.rename(columns={"geometry": "geom"}).set_geometry("geom")
        frames.append(gdf[["council", "path_class", "confidence", "georef_mode", "geom"]])

    if not frames:
        print("WARNING: council overlay files were empty/unreadable")
        return

    combined = gpd.GeoDataFrame(
        pd_concat(frames),
        geometry="geom",
        crs="EPSG:7850",
    )
    combined.to_postgis("council_overlay", engine, if_exists="replace", index=False)
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_council_overlay_geom ON council_overlay USING GIST (geom)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_council_overlay_class ON council_overlay (path_class)"))
    print(f"Loaded {len(combined)} council overlay features")


def pd_concat(frames):
    import pandas as pd

    return pd.concat(frames, ignore_index=True)


def classify_psp_from_ltcn(engine):
    """Upgrade edges to PSP where they spatially match LTCN Primary Routes."""
    print(f"Matching LTCN Primary Routes to OSM edges (buffer={MATCH_BUFFER_M}m)...")

    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE edge e
            SET facility_class = 'PSP',
                psp_flag = TRUE,
                psp_source = 'ltcn_primary'
            FROM ltcn_overlay l
            WHERE l.hierarchy = 'Primary Route'
              AND ST_DWithin(e.geom, l.geom, :buffer)
              AND e.facility_class IN (
                  'OFFROAD_SHARED_PATH_HQ',
                  'OFFROAD_SHARED_PATH',
                  'CYCLE_TRACK_PROTECTED'
              )
        """), {"buffer": MATCH_BUFFER_M})
        print(f"Upgraded {result.rowcount} edges to PSP via LTCN Primary Route match")


def classify_psp_from_mrwa(engine):
    """Upgrade edges to PSP where they match MRWA controlled paths with PSP nodes."""
    print(f"Matching MRWA PSP nodes to OSM edges (buffer={MATCH_BUFFER_M}m)...")

    with engine.begin() as conn:
        # Find edges near MRWA controlled paths that connect to PSP nodes
        result = conn.execute(text("""
            UPDATE edge e
            SET facility_class = 'PSP',
                psp_flag = TRUE,
                psp_source = 'mrwa_psp_nodes'
            FROM mrwa_road_asset r, mrwa_intersection i
            WHERE ST_DWithin(e.geom, r.geom, :buffer)
              AND ST_DWithin(r.geom, i.geom, :buffer)
              AND e.psp_flag = FALSE
              AND e.facility_class IN (
                  'OFFROAD_SHARED_PATH_HQ',
                  'OFFROAD_SHARED_PATH',
                  'CYCLE_TRACK_PROTECTED'
              )
        """), {"buffer": MATCH_BUFFER_M})
        print(f"Upgraded {result.rowcount} edges to PSP via MRWA PSP node match")


def classify_from_council_overlays(engine):
    """Apply council PDF-derived overlays as highest-priority classification source."""
    print("Matching council overlays to OSM edges (buffer=20m)...")

    with engine.begin() as conn:
        exists = conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'council_overlay'
                )
                """
            )
        ).scalar()
        if not exists:
            print("Council overlay table not found, skipping council overlay classification")
            return

        # High-confidence dedicated council lines: mark as PSP.
        psp_result = conn.execute(
            text(
                """
                WITH council_mask AS (
                    SELECT ST_Union(ST_Buffer(c.geom, :buffer)) AS geom
                    FROM council_overlay c
                    WHERE c.path_class IN ('psp', 'shared_path')
                      AND c.confidence >= CASE
                          WHEN c.georef_mode = 'fallback_bbox' THEN 0.45
                          ELSE 0.55
                      END
                )
                UPDATE edge e
                SET facility_class = 'PSP',
                    psp_flag = TRUE,
                    psp_source = 'manual'
                FROM council_mask m
                WHERE m.geom IS NOT NULL
                  AND ST_Intersects(e.geom, m.geom)
                """
            ),
            {"buffer": 20},
        )
        print(f"Upgraded {psp_result.rowcount} edges to PSP via council overlay")

        # Medium-confidence bike-lane council lines: upgrade noisy roads to painted cycle lanes.
        lane_result = conn.execute(
            text(
                """
                WITH lane_mask AS (
                    SELECT ST_Union(ST_Buffer(c.geom, :buffer)) AS geom
                    FROM council_overlay c
                    WHERE c.path_class = 'bike_lane'
                      AND c.confidence >= 0.35
                )
                UPDATE edge e
                SET facility_class = 'CYCLE_LANE_PAINTED'
                FROM lane_mask m
                WHERE m.geom IS NOT NULL
                  AND e.facility_class = 'BUSY_ROAD_NO_INFRA'
                  AND ST_Intersects(e.geom, m.geom)
                """
            ),
            {"buffer": 20},
        )
        print(f"Upgraded {lane_result.rowcount} edges to CYCLE_LANE_PAINTED via council overlay")


def compute_crash_risk(engine):
    """Compute crash risk score for each edge based on nearby bike crashes."""
    print("Computing crash risk scores...")

    # Use a 100m buffer and inverse distance weighting
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE edge e
            SET crash_risk = LEAST(1.0, sub.risk_score)
            FROM (
                SELECT e2.edge_id,
                       COALESCE(SUM(1.0 / GREATEST(ST_Distance(e2.geom, c.geom), 1.0)), 0) / 10.0
                           AS risk_score
                FROM edge e2
                LEFT JOIN mrwa_crash c
                    ON ST_DWithin(e2.geom, c.geom, 100)
                GROUP BY e2.edge_id
            ) sub
            WHERE e.edge_id = sub.edge_id
        """))
        print("Crash risk scores computed")


def print_classification_summary(engine):
    """Print summary of edge classification."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT facility_class,
                   COUNT(*) as edge_count,
                   ROUND(SUM(length_m)::numeric / 1000, 1) as total_km
            FROM edge
            GROUP BY facility_class
            ORDER BY total_km DESC
        """))
        print("\n=== Edge Classification Summary ===")
        print(f"{'Facility Class':<30} {'Edges':>8} {'Total km':>10}")
        print("-" * 50)
        for row in result:
            print(f"{row[0]:<30} {row[1]:>8} {row[2]:>10}")

        psp_result = conn.execute(text("""
            SELECT COUNT(*), ROUND(SUM(length_m)::numeric / 1000, 1)
            FROM edge WHERE psp_flag = TRUE
        """))
        psp_row = psp_result.fetchone()
        print(f"\nPSP edges: {psp_row[0]} ({psp_row[1]} km)")


def main():
    engine = create_engine(DB_URL)

    print("=== PSP Edge Classification ===")
    load_ltcn_to_postgis(engine)
    load_mrwa_to_postgis(engine)
    load_council_overlays_to_postgis(engine)
    classify_psp_from_ltcn(engine)
    classify_psp_from_mrwa(engine)
    classify_from_council_overlays(engine)
    compute_crash_risk(engine)
    print_classification_summary(engine)
    print("Classification complete.")


if __name__ == "__main__":
    main()
