"""Export classified graph data for GraphHopper and API consumption."""

import json
import os

import geopandas as gpd
from shapely.geometry import Polygon, mapping
from shapely.ops import unary_union
from sqlalchemy import create_engine, text

DATA_DIR = os.environ.get("DATA_DIR", "/data")

DB_URL = (
    f"postgresql://{os.environ.get('POSTGRES_USER', 'psp')}:"
    f"{os.environ.get('POSTGRES_PASSWORD', 'psp_dev_password')}@"
    f"{os.environ.get('POSTGRES_HOST', 'localhost')}:"
    f"{os.environ.get('POSTGRES_PORT', '5432')}/"
    f"{os.environ.get('POSTGRES_DB', 'perth_psp')}"
)


def export_psp_layer(engine):
    """Export PSP edges as GeoJSON for the frontend overlay layer."""
    output_dir = os.path.join(DATA_DIR, "export")
    os.makedirs(output_dir, exist_ok=True)

    print("Exporting PSP layer...")
    gdf = gpd.read_postgis(
        """
        SELECT edge_id, facility_class, psp_flag, psp_source, length_m, crash_risk,
               ST_Transform(geom, 4326) as geom
        FROM edge
        WHERE psp_flag = TRUE
        """,
        engine,
        geom_col="geom",
    )

    output = os.path.join(output_dir, "psp_network.geojson")
    gdf.to_file(output, driver="GeoJSON")
    print(f"Exported {len(gdf)} PSP edges to {output}")


def export_psp_way_priority_map(engine):
    """Export WA-informed PSP ranking keyed by OSM way id."""
    output_dir = os.path.join(DATA_DIR, "export")
    os.makedirs(output_dir, exist_ok=True)

    print("Exporting PSP way priority map...")
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT
                    osm_way_id,
                    BOOL_OR(psp_flag) AS psp_flag,
                    MAX(
                        CASE
                            WHEN psp_source = 'manual' THEN 130
                            WHEN psp_source = 'mrwa_psp_nodes' THEN 120
                            WHEN psp_source = 'ltcn_primary' THEN 110
                            WHEN psp_flag THEN 100
                            WHEN facility_class IN ('OFFROAD_SHARED_PATH_HQ', 'CYCLE_TRACK_PROTECTED') THEN 80
                            WHEN facility_class = 'OFFROAD_SHARED_PATH' THEN 70
                            WHEN facility_class = 'CYCLE_LANE_PAINTED' THEN 50
                            WHEN facility_class = 'QUIET_STREET' THEN 30
                            ELSE 10
                        END
                    ) AS priority_rank,
                    STRING_AGG(DISTINCT COALESCE(psp_source::text, 'osm_only'), ',') AS psp_sources
                FROM edge
                WHERE osm_way_id IS NOT NULL
                GROUP BY osm_way_id
                """
            )
        )
        rows = result.fetchall()

    payload = {
        "version": 1,
        "description": "WA-informed PSP ranking keyed by OSM way id",
        "items": [
            {
                "osm_way_id": str(int(row.osm_way_id)),
                "psp_flag": bool(row.psp_flag),
                "priority_rank": int(row.priority_rank),
                "psp_sources": sorted(
                    {
                        ("council_pdf" if source == "manual" else source)
                        for source in (row.psp_sources.split(",") if row.psp_sources else [])
                        if source
                    }
                ),
            }
            for row in rows
        ],
    }

    output = os.path.join(output_dir, "psp_way_priority.json")
    with open(output, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Exported {len(payload['items'])} OSM way rankings to {output}")


def export_council_overlay_layer(engine):
    """Export council-derived overlay lines for QA and map debugging."""
    output_dir = os.path.join(DATA_DIR, "export")
    os.makedirs(output_dir, exist_ok=True)

    print("Exporting council overlay layer...")
    try:
        gdf = gpd.read_postgis(
            """
            SELECT council, path_class, confidence, ST_Transform(geom, 4326) AS geom
            FROM council_overlay
            """,
            engine,
            geom_col="geom",
        )
        output = os.path.join(output_dir, "council_overlay.geojson")
        gdf.to_file(output, driver="GeoJSON")
        print(f"Exported {len(gdf)} council overlay features to {output}")
    except Exception as exc:
        print(f"Warning: Could not export council overlay layer: {exc}")


def export_graphhopper_custom_areas(engine):
    """Export WA-derived corridor polygons for GraphHopper custom areas."""
    output_dir = os.path.join(DATA_DIR, "export", "areas")
    os.makedirs(output_dir, exist_ok=True)

    print("Exporting GraphHopper custom areas...")
    psp_edges = gpd.read_postgis(
        """
        SELECT ST_Transform(geom, 7850) AS geom
        FROM edge
        WHERE psp_flag = TRUE
        """,
        engine,
        geom_col="geom",
    )
    offroad_edges = gpd.read_postgis(
        """
        SELECT ST_Transform(geom, 7850) AS geom
        FROM edge
        WHERE facility_class IN (
            'PSP',
            'OFFROAD_SHARED_PATH_HQ',
            'OFFROAD_SHARED_PATH',
            'CYCLE_TRACK_PROTECTED'
        )
        """,
        engine,
        geom_col="geom",
    )

    # Fallback tiny polygon keeps schema valid if data is unavailable.
    fallback_geom = Polygon(
        [(0.0, 0.0), (0.0, 0.001), (0.001, 0.001), (0.001, 0.0), (0.0, 0.0)]
    )

    if len(psp_edges) > 0:
        psp_union = unary_union(psp_edges.buffer(30).geometry)
        psp_geom = gpd.GeoSeries([psp_union], crs="EPSG:7850").to_crs("EPSG:4326").iloc[0]
    else:
        psp_geom = fallback_geom

    if len(offroad_edges) > 0:
        offroad_union = unary_union(offroad_edges.buffer(20).geometry)
        offroad_geom = (
            gpd.GeoSeries([offroad_union], crs="EPSG:7850").to_crs("EPSG:4326").iloc[0]
        )
    else:
        offroad_geom = fallback_geom

    custom_areas = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "psp_corridor",
                "properties": {"source": "wa_overlay"},
                "geometry": mapping(psp_geom),
            },
            {
                "type": "Feature",
                "id": "offroad_corridor",
                "properties": {"source": "osm_wa_overlay"},
                "geometry": mapping(offroad_geom),
            },
        ],
    }

    output = os.path.join(output_dir, "graphhopper_custom_areas.geojson")
    with open(output, "w", encoding="utf-8") as f:
        json.dump(custom_areas, f)
    print(f"Exported GraphHopper custom areas to {output}")


def export_infrastructure_layer(engine):
    """Export all cycling infrastructure as GeoJSON for the frontend."""
    output_dir = os.path.join(DATA_DIR, "export")
    os.makedirs(output_dir, exist_ok=True)

    print("Exporting infrastructure layer...")
    gdf = gpd.read_postgis(
        """
        SELECT edge_id, facility_class, psp_flag, length_m,
               ST_Transform(geom, 4326) as geom
        FROM edge
        WHERE facility_class != 'BUSY_ROAD_NO_INFRA'
        """,
        engine,
        geom_col="geom",
    )

    output = os.path.join(output_dir, "cycling_infrastructure.geojson")
    gdf.to_file(output, driver="GeoJSON")
    print(f"Exported {len(gdf)} infrastructure edges to {output}")


def export_crash_hotspots(engine):
    """Export crash data as GeoJSON for the frontend."""
    output_dir = os.path.join(DATA_DIR, "export")
    os.makedirs(output_dir, exist_ok=True)

    print("Exporting crash hotspots...")
    try:
        gdf = gpd.read_postgis(
            """
            SELECT id, severity, crash_date, total_bike_involved,
                   ST_Transform(geom, 4326) as geom
            FROM mrwa_crash
            """,
            engine,
            geom_col="geom",
        )

        output = os.path.join(output_dir, "crash_hotspots.geojson")
        gdf.to_file(output, driver="GeoJSON")
        print(f"Exported {len(gdf)} crash hotspots to {output}")
    except Exception as e:
        print(f"Warning: Could not export crash data: {e}")


def main():
    engine = create_engine(DB_URL)

    print("=== Exporting Router Data ===")
    export_psp_layer(engine)
    export_council_overlay_layer(engine)
    export_psp_way_priority_map(engine)
    export_graphhopper_custom_areas(engine)
    export_infrastructure_layer(engine)
    export_crash_hotspots(engine)
    print("Export complete.")


if __name__ == "__main__":
    main()
