"""Download Your Move council bike maps (PDF-first source stage)."""

import json
import os
import urllib.request
from pathlib import Path

DATA_DIR = os.environ.get("DATA_DIR", "/data")
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_data_sources() -> dict:
    with open(CONFIG_DIR / "data_sources.json", encoding="utf-8") as f:
        return json.load(f)


def download_council_maps() -> tuple[Path, int]:
    sources = load_data_sources()
    maps = sources.get("yourmove_council_maps", {}).get("metro_pdfs", [])
    raw_dir = Path(DATA_DIR) / "council_maps" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    for entry in maps:
        council = entry["council"]
        year = entry.get("edition_year", "unknown")
        url = entry["pdf_url"]
        out_name = f"{council}_{year}.pdf"
        out_path = raw_dir / out_name

        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"Council map already exists: {out_path}")
            continue

        print(f"Downloading council map {council} from {url}")
        urllib.request.urlretrieve(url, out_path)  # nosec B310 - controlled source list
        downloaded += 1
        print(f"Saved: {out_path}")

    return raw_dir, downloaded


def main():
    print("=== Downloading council bike map PDFs ===")
    raw_dir, downloaded = download_council_maps()
    print(f"Council map raw directory: {raw_dir}")
    print(f"New downloads: {downloaded}")


if __name__ == "__main__":
    main()
