"""Run the full ETL pipeline."""

from pathlib import Path
import runpy


SCRIPTS = [
    ("01_download_osm.py", "Downloading OSM data"),
    ("02_download_wa_datasets.py", "Downloading WA government datasets"),
    ("06_download_council_maps.py", "Downloading council bike map PDFs"),
    ("07_extract_council_map_network.py", "Extracting council bike network overlays"),
    ("03_build_graph.py", "Building cycling graph"),
    ("04_classify_edges.py", "Classifying PSP edges"),
    ("05_export_router_data.py", "Exporting router data"),
]


def main():
    print("=" * 60)
    print("Perth PSP-Priority ETL Pipeline")
    print("=" * 60)

    scripts_dir = Path(__file__).resolve().parent
    total = len(SCRIPTS)

    for idx, (filename, description) in enumerate(SCRIPTS, start=1):
        script_path = scripts_dir / filename
        print(f"\n[{idx}/{total}] {description}...")
        runpy.run_path(str(script_path), run_name="__main__")

    print("\n" + "=" * 60)
    print("ETL pipeline complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
