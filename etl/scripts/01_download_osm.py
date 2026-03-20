"""Download and filter OSM data to Perth metro bounding box."""

import json
import os
import subprocess
import urllib.request

DATA_DIR = os.environ.get("DATA_DIR", "/data")
OSM_DIR = os.path.join(DATA_DIR, "osm")
CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "config")

GEOFABRIK_URL = "https://download.geofabrik.de/australia-oceania/australia-latest.osm.pbf"


def load_bbox() -> dict:
    with open(os.path.join(CONFIG_DIR, "perth_metro_bbox.json")) as f:
        return json.load(f)


def download_osm_extract():
    """Download the Australia PBF extract from Geofabrik."""
    os.makedirs(OSM_DIR, exist_ok=True)
    output = os.path.join(OSM_DIR, "australia-latest.osm.pbf")

    if os.path.exists(output):
        print(f"OSM extract already exists: {output}")
        return output

    print(f"Downloading OSM extract from {GEOFABRIK_URL}...")
    urllib.request.urlretrieve(GEOFABRIK_URL, output)
    print(f"Downloaded to {output}")
    return output


def filter_to_perth(input_pbf: str) -> str:
    """Filter the Australia PBF to Perth metro bounding box using osmium."""
    bbox = load_bbox()
    output = os.path.join(OSM_DIR, "perth-metro.osm.pbf")

    bbox_str = f"{bbox['west']},{bbox['south']},{bbox['east']},{bbox['north']}"

    print(f"Filtering OSM extract to Perth metro bbox: {bbox_str}")
    subprocess.run(
        [
            "osmium",
            "extract",
            "--bbox",
            bbox_str,
            "--strategy",
            "smart",
            "--output",
            output,
            "--overwrite",
            input_pbf,
        ],
        check=True,
    )
    print(f"Filtered extract: {output}")
    return output


def main():
    australia_pbf = download_osm_extract()
    perth_pbf = filter_to_perth(australia_pbf)
    print(f"Perth metro OSM extract ready: {perth_pbf}")
    return perth_pbf


if __name__ == "__main__":
    main()
