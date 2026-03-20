"""Download WA government datasets (DoT LTCN, MRWA layers) via ArcGIS REST APIs."""

import json
import os
import urllib.request
import zipfile

import requests

DATA_DIR = os.environ.get("DATA_DIR", "/data")
CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "config")


def load_data_sources() -> dict:
    with open(os.path.join(CONFIG_DIR, "data_sources.json")) as f:
        return json.load(f)


def load_bbox() -> dict:
    with open(os.path.join(CONFIG_DIR, "perth_metro_bbox.json")) as f:
        return json.load(f)


def download_ltcn_shapefile():
    """Download DoT Long-Term Cycle Network shapefile from Data WA."""
    sources = load_data_sources()
    url = sources["dot_ltcn"]["shapefile_url"]
    ltcn_dir = os.path.join(DATA_DIR, "ltcn")
    os.makedirs(ltcn_dir, exist_ok=True)

    zip_path = os.path.join(ltcn_dir, "ltcn.shp.zip")

    if os.path.exists(zip_path):
        print(f"LTCN shapefile already downloaded: {zip_path}")
    else:
        print(f"Downloading LTCN shapefile from {url}...")
        urllib.request.urlretrieve(url, zip_path)
        print(f"Downloaded to {zip_path}")

    # Extract
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(ltcn_dir)
    print(f"Extracted LTCN shapefile to {ltcn_dir}")
    return ltcn_dir


def query_arcgis_layer(base_url: str, where: str = "1=1", bbox: dict | None = None,
                        out_fields: str = "*", max_records: int = 2000) -> list[dict]:
    """Query an ArcGIS REST MapServer layer with pagination."""
    all_features = []
    offset = 0

    geometry_filter = None
    if bbox:
        geometry_filter = {
            "xmin": bbox["west"],
            "ymin": bbox["south"],
            "xmax": bbox["east"],
            "ymax": bbox["north"],
            "spatialReference": {"wkid": 4326},
        }

    while True:
        params = {
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": max_records,
        }
        if geometry_filter:
            params["geometry"] = json.dumps(geometry_filter)
            params["geometryType"] = "esriGeometryEnvelope"
            params["spatialRel"] = "esriSpatialRelIntersects"
            params["inSR"] = "4326"

        response = requests.get(f"{base_url}/query", params=params, timeout=60)
        response.raise_for_status()
        data = response.json()

        features = data.get("features", [])
        if not features:
            break

        all_features.extend(features)
        print(f"  Fetched {len(features)} features (total: {len(all_features)})")

        if len(features) < max_records:
            break
        offset += max_records

    return all_features


def download_mrwa_layers():
    """Download MRWA datasets via ArcGIS REST API."""
    sources = load_data_sources()
    bbox = load_bbox()
    mrwa_dir = os.path.join(DATA_DIR, "mrwa")
    os.makedirs(mrwa_dir, exist_ok=True)

    layers = {
        "road_network": {
            "url": sources["mrwa_road_network"]["arcgis_rest"],
            "where": "NETWORK_TYPE = 'Main Roads Controlled Path'",
        },
        "intersections": {
            "url": sources["mrwa_intersections"]["arcgis_rest"],
            "where": "NODE_TYPE = 'Principal Shared Path Node'",
        },
        "crashes": {
            "url": sources["mrwa_crashes"]["arcgis_rest"],
            "where": "TOTAL_BIKE_INVOLVED > 0",
        },
        "speed_zones": {
            "url": sources["mrwa_speed_zones"]["arcgis_rest"],
            "where": "1=1",
        },
        "road_hierarchy": {
            "url": sources["mrwa_road_hierarchy"]["arcgis_rest"],
            "where": "1=1",
        },
    }

    for name, config in layers.items():
        output_path = os.path.join(mrwa_dir, f"{name}.geojson")
        if os.path.exists(output_path):
            print(f"MRWA {name} already downloaded: {output_path}")
            continue

        print(f"Downloading MRWA {name}...")
        features = query_arcgis_layer(
            config["url"],
            where=config["where"],
            bbox=bbox,
        )

        geojson = {
            "type": "FeatureCollection",
            "features": features,
        }

        with open(output_path, "w") as f:
            json.dump(geojson, f)
        print(f"Saved {len(features)} features to {output_path}")

    return mrwa_dir


def main():
    print("=== Downloading WA Government Datasets ===")
    ltcn_dir = download_ltcn_shapefile()
    mrwa_dir = download_mrwa_layers()
    print(f"\nLTCN data: {ltcn_dir}")
    print(f"MRWA data: {mrwa_dir}")


if __name__ == "__main__":
    main()
