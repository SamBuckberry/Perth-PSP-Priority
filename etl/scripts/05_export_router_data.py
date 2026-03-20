"""Export classified graph data for GraphHopper consumption.

Generates a custom OSM PBF file with PSP tags encoded as custom OSM tags
that GraphHopper's custom model can reference.
"""

import json
import os

import geopandas as gpd
from pyproj import Transformer
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
    export_infrastructure_layer(engine)
    export_crash_hotspots(engine)
    print("Export complete.")


if __name__ == "__main__":
    main()
