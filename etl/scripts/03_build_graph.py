"""Build the cycling graph from OSM data and load into PostGIS."""

import json
import os

import geopandas as gpd
import osmnx as ox
from pyproj import Transformer
from sqlalchemy import create_engine, text

DATA_DIR = os.environ.get("DATA_DIR", "/data")
CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "config")

DB_URL = (
    f"postgresql://{os.environ.get('POSTGRES_USER', 'psp')}:"
    f"{os.environ.get('POSTGRES_PASSWORD', 'psp_dev_password')}@"
    f"{os.environ.get('POSTGRES_HOST', 'localhost')}:"
    f"{os.environ.get('POSTGRES_PORT', '5432')}/"
    f"{os.environ.get('POSTGRES_DB', 'perth_psp')}"
)


def load_bbox() -> tuple[float, float, float, float]:
    with open(os.path.join(CONFIG_DIR, "perth_metro_bbox.json")) as f:
        bbox = json.load(f)
    return bbox["north"], bbox["south"], bbox["east"], bbox["west"]


def download_cycling_graph():
    """Download cycling network from OSM using osmnx."""
    north, south, east, west = load_bbox()

    print("Downloading cycling network from OSM via osmnx...")
    G = ox.graph_from_bbox(
        bbox=(west, south, east, north),
        network_type="bike",
        retain_all=True,
    )
    print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    return G


def graph_to_geodataframes(G):
    """Convert osmnx graph to node and edge GeoDataFrames."""
    nodes_gdf, edges_gdf = ox.graph_to_gdfs(G)

    # Ensure CRS is WGS84 first
    if nodes_gdf.crs is None:
        nodes_gdf = nodes_gdf.set_crs("EPSG:4326")
    if edges_gdf.crs is None:
        edges_gdf = edges_gdf.set_crs("EPSG:4326")

    # Reproject to MGA Zone 50 (EPSG:7850)
    nodes_gdf = nodes_gdf.to_crs("EPSG:7850")
    edges_gdf = edges_gdf.to_crs("EPSG:7850")

    return nodes_gdf, edges_gdf


def classify_osm_tags(row) -> str:
    """Classify an OSM way into a facility_class based on tags."""
    highway = row.get("highway", "")
    cycleway = row.get("cycleway", "")
    bicycle = row.get("bicycle", "")

    # Handle lists (osmnx sometimes returns lists for multi-valued tags)
    if isinstance(highway, list):
        highway = highway[0] if highway else ""
    if isinstance(cycleway, list):
        cycleway = cycleway[0] if cycleway else ""
    if isinstance(bicycle, list):
        bicycle = bicycle[0] if bicycle else ""

    # Dedicated cycleway
    if highway == "cycleway":
        return "OFFROAD_SHARED_PATH_HQ"

    # Designated bike path
    if highway == "path" and bicycle == "designated":
        return "OFFROAD_SHARED_PATH"

    # Protected cycle track
    if cycleway == "track":
        return "CYCLE_TRACK_PROTECTED"

    # Painted cycle lane
    if cycleway in ("lane", "shared_lane"):
        return "CYCLE_LANE_PAINTED"

    # Quiet residential streets
    if highway in ("residential", "living_street", "service"):
        return "QUIET_STREET"

    # Footpath / pedestrian (legal cycling in WA on footpaths)
    if highway in ("footway", "pedestrian", "path"):
        return "OFFROAD_SHARED_PATH"

    # Anything else (primary, secondary, tertiary, trunk, etc.)
    return "BUSY_ROAD_NO_INFRA"


def load_to_postgis(nodes_gdf: gpd.GeoDataFrame, edges_gdf: gpd.GeoDataFrame):
    """Load nodes and edges into PostGIS."""
    engine = create_engine(DB_URL)

    print("Loading nodes into PostGIS...")
    # Prepare nodes
    nodes_df = nodes_gdf.reset_index()
    nodes_df = nodes_df.rename(columns={"osmid": "osm_node_id"})
    nodes_df["is_psp_node_mrwa"] = False
    nodes_upload = nodes_df[["osm_node_id", "geometry", "is_psp_node_mrwa"]].copy()
    nodes_upload = nodes_upload.rename(columns={"geometry": "geom"})
    nodes_upload = gpd.GeoDataFrame(nodes_upload, geometry="geom", crs="EPSG:7850")

    nodes_upload.to_postgis("node", engine, if_exists="append", index=False)
    print(f"Loaded {len(nodes_upload)} nodes")

    print("Loading edges into PostGIS...")
    # Prepare edges
    edges_df = edges_gdf.reset_index()

    # Calculate length in metres
    edges_df["length_m"] = edges_df.geometry.length

    # Classify facility type from OSM tags
    edges_df["facility_class"] = edges_df.apply(classify_osm_tags, axis=1)

    # Extract surface/lit info
    edges_df["surface"] = edges_df.get("surface", None)
    edges_df["smoothness"] = edges_df.get("smoothness", None)
    edges_df["lit"] = edges_df.get("lit", "").apply(
        lambda x: True if x == "yes" else (False if x == "no" else None)
    ) if "lit" in edges_df.columns else None

    edges_upload = edges_df[
        ["osmid", "geometry", "length_m", "facility_class", "surface", "smoothness"]
    ].copy()
    edges_upload = edges_upload.rename(
        columns={"osmid": "osm_way_id", "geometry": "geom"}
    )
    edges_upload["psp_flag"] = False
    edges_upload["psp_source"] = None
    edges_upload["crash_risk"] = 0.0

    edges_upload = gpd.GeoDataFrame(edges_upload, geometry="geom", crs="EPSG:7850")
    edges_upload.to_postgis("edge", engine, if_exists="append", index=False)
    print(f"Loaded {len(edges_upload)} edges")


def main():
    print("=== Building Perth Cycling Graph ===")
    G = download_cycling_graph()
    nodes_gdf, edges_gdf = graph_to_geodataframes(G)
    load_to_postgis(nodes_gdf, edges_gdf)
    print("Graph build complete.")


if __name__ == "__main__":
    main()
