"""Run the full ETL pipeline."""

from scripts import (
    # Step 1 and 2 can be run independently
)
from scripts.01_download_osm import main as download_osm
from scripts.02_download_wa_datasets import main as download_wa
from scripts.03_build_graph import main as build_graph
from scripts.04_classify_edges import main as classify_edges
from scripts.05_export_router_data import main as export_data


def main():
    print("=" * 60)
    print("Perth PSP-Priority ETL Pipeline")
    print("=" * 60)

    print("\n[1/5] Downloading OSM data...")
    download_osm()

    print("\n[2/5] Downloading WA government datasets...")
    download_wa()

    print("\n[3/5] Building cycling graph...")
    build_graph()

    print("\n[4/5] Classifying PSP edges...")
    classify_edges()

    print("\n[5/5] Exporting router data...")
    export_data()

    print("\n" + "=" * 60)
    print("ETL pipeline complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
