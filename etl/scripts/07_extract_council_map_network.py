"""Extract bike network vectors from council GeoPDF maps (PDF-first stage)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import fitz
import geopandas as gpd
import numpy as np
from pypdf import PdfReader
from pyproj import Transformer
from shapely.geometry import LineString
from shapely.ops import linemerge, unary_union

DATA_DIR = os.environ.get("DATA_DIR", "/data")
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
EXTRACT_VERSION = "pdf-first-v1"


@dataclass
class PageGeoTransform:
    page_number: int
    bbox: tuple[float, float, float, float]
    lon_coeff: np.ndarray
    lat_coeff: np.ndarray
    georef_mode: str = "embedded"

    def to_lon_lat(self, x: float, y: float) -> tuple[float, float]:
        lon = (self.lon_coeff[0] * x) + (self.lon_coeff[1] * y) + self.lon_coeff[2]
        lat = (self.lat_coeff[0] * x) + (self.lat_coeff[1] * y) + self.lat_coeff[2]
        return float(lon), float(lat)


def load_data_sources() -> dict[str, Any]:
    with open(CONFIG_DIR / "data_sources.json", encoding="utf-8") as f:
        return json.load(f)


def load_bbox() -> dict[str, float]:
    with open(CONFIG_DIR / "perth_metro_bbox.json", encoding="utf-8") as f:
        return json.load(f)


def _to_float_list(values: Any) -> list[float]:
    if values is None:
        return []
    return [float(v) for v in values]


def _normalised_to_page_xy(nx: float, ny: float, bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    x_min, y_min, x_max, y_max = bbox
    return (
        x_min + (nx * (x_max - x_min)),
        y_min + (ny * (y_max - y_min)),
    )


def _to_lon_lat_pairs(gpts: list[float]) -> list[tuple[float, float]]:
    pairs = [(gpts[i], gpts[i + 1]) for i in range(0, len(gpts), 2)]
    if not pairs:
        return []

    first = [p[0] for p in pairs]
    second = [p[1] for p in pairs]

    first_is_lat = all(abs(v) <= 90 for v in first)
    second_is_lat = all(abs(v) <= 90 for v in second)
    first_is_lon = all(abs(v) <= 180 for v in first)
    second_is_lon = all(abs(v) <= 180 for v in second)

    if first_is_lat and second_is_lon:
        return [(lon, lat) for lat, lon in pairs]
    if first_is_lon and second_is_lat:
        return pairs
    return pairs


def _build_affine(page_points: list[tuple[float, float]], lon_lat_points: list[tuple[float, float]]) -> tuple[np.ndarray, np.ndarray]:
    a = np.array([[x, y, 1.0] for x, y in page_points], dtype=np.float64)
    lon = np.array([ll[0] for ll in lon_lat_points], dtype=np.float64)
    lat = np.array([ll[1] for ll in lon_lat_points], dtype=np.float64)
    lon_coeff, *_ = np.linalg.lstsq(a, lon, rcond=None)
    lat_coeff, *_ = np.linalg.lstsq(a, lat, rcond=None)
    return lon_coeff, lat_coeff


def read_page_georeference(reader: PdfReader, page_number: int) -> Optional[PageGeoTransform]:
    page_obj = reader.pages[page_number]
    vp = page_obj.get("/VP")
    if vp is None:
        return None

    vp_items = vp if isinstance(vp, list) else [vp]
    for item in vp_items:
        vp_dict = item.get_object() if hasattr(item, "get_object") else item
        measure_ref = vp_dict.get("/Measure")
        bbox_vals = _to_float_list(vp_dict.get("/BBox"))
        if not measure_ref or len(bbox_vals) != 4:
            continue
        measure = measure_ref.get_object() if hasattr(measure_ref, "get_object") else measure_ref
        gpts = _to_float_list(measure.get("/GPTS"))
        lpts = _to_float_list(measure.get("/LPTS"))
        if len(gpts) < 8 or len(lpts) < 8:
            continue

        lon_lat_points = _to_lon_lat_pairs(gpts)
        lpt_pairs = [(lpts[i], lpts[i + 1]) for i in range(0, len(lpts), 2)]
        pair_count = min(len(lon_lat_points), len(lpt_pairs))
        if pair_count < 4:
            continue

        bbox = (bbox_vals[0], bbox_vals[1], bbox_vals[2], bbox_vals[3])
        page_points = [
            _normalised_to_page_xy(lpt_pairs[i][0], lpt_pairs[i][1], bbox) for i in range(pair_count)
        ]
        lon_coeff, lat_coeff = _build_affine(page_points, lon_lat_points[:pair_count])
        return PageGeoTransform(
            page_number=page_number + 1,
            bbox=bbox,
            lon_coeff=lon_coeff,
            lat_coeff=lat_coeff,
            georef_mode="embedded",
        )
    return None


def build_fallback_page_transform(page: fitz.Page, page_number: int, fallback_bbox: dict[str, float]) -> PageGeoTransform:
    """Fallback georeference by mapping page extents to configured council bbox."""
    rect = page.rect
    page_points = [
        (rect.x0, rect.y1),  # south-west
        (rect.x1, rect.y1),  # south-east
        (rect.x1, rect.y0),  # north-east
        (rect.x0, rect.y0),  # north-west
    ]
    lon_lat_points = [
        (fallback_bbox["west"], fallback_bbox["south"]),
        (fallback_bbox["east"], fallback_bbox["south"]),
        (fallback_bbox["east"], fallback_bbox["north"]),
        (fallback_bbox["west"], fallback_bbox["north"]),
    ]
    lon_coeff, lat_coeff = _build_affine(page_points, lon_lat_points)
    return PageGeoTransform(
        page_number=page_number + 1,
        bbox=(rect.x0, rect.y0, rect.x1, rect.y1),
        lon_coeff=lon_coeff,
        lat_coeff=lat_coeff,
        georef_mode="fallback_bbox",
    )


def _drawing_segments(drawing: dict[str, Any]) -> list[LineString]:
    segments: list[LineString] = []
    for item in drawing.get("items", []):
        if not item:
            continue
        op = item[0]
        if op == "l" and len(item) >= 3:
            p1, p2 = item[1], item[2]
            segments.append(LineString([(p1.x, p1.y), (p2.x, p2.y)]))
        elif op == "c" and len(item) >= 5:
            p1, p4 = item[1], item[4]
            segments.append(LineString([(p1.x, p1.y), (p4.x, p4.y)]))
    return segments


def _classify_path(color: tuple[float, float, float] | None, width: float) -> tuple[str, float]:
    if color is None:
        return "unknown", 0.2
    r, g, b = color
    if g > (r * 1.12) and g > (b * 1.05):
        if width >= 1.6:
            return "psp", 0.92
        if width >= 0.9:
            return "shared_path", 0.78
        return "quiet_street", 0.45
    if b > (g * 1.08) and b > (r * 1.05):
        return "bike_lane", 0.55
    if width < 0.7:
        return "quiet_street", 0.35
    return "unknown", 0.25


def _in_perth_bbox(lon: float, lat: float, bbox: dict[str, float]) -> bool:
    return bbox["west"] <= lon <= bbox["east"] and bbox["south"] <= lat <= bbox["north"]


def extract_pdf_vectors(
    pdf_path: Path,
    council: str,
    edition_year: int,
    bbox: dict[str, float],
    fallback_bbox: Optional[dict[str, float]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    reader = PdfReader(str(pdf_path))
    doc = fitz.open(str(pdf_path))
    features: list[dict[str, Any]] = []
    page_summary: list[dict[str, Any]] = []

    metric_transformer = Transformer.from_crs("EPSG:4326", "EPSG:7850", always_xy=True)

    for page_idx in range(len(doc)):
        geo = read_page_georeference(reader, page_idx)
        if not geo and fallback_bbox:
            geo = build_fallback_page_transform(doc[page_idx], page_idx, fallback_bbox)
        if not geo:
            page_summary.append({"page": page_idx + 1, "georef": False, "features": 0})
            continue

        page = doc[page_idx]
        drawings = page.get_drawings()
        page_count = 0
        for drawing in drawings:
            color = drawing.get("color")
            width_raw = drawing.get("width")
            width = float(width_raw) if width_raw is not None else 1.0
            segments = _drawing_segments(drawing)
            if not segments:
                continue

            if len(segments) == 1:
                lines = segments
            else:
                try:
                    merged = linemerge(unary_union(segments))
                    lines = [merged] if merged.geom_type == "LineString" else list(merged.geoms)
                except Exception:
                    lines = segments
            for line in lines:
                if line.length < 40:
                    continue
                lon_lat_coords = [geo.to_lon_lat(x, y) for x, y in line.coords]
                if not lon_lat_coords:
                    continue
                if not any(_in_perth_bbox(lon, lat, bbox) for lon, lat in lon_lat_coords):
                    continue

                projected = [
                    metric_transformer.transform(lon, lat) for lon, lat in lon_lat_coords
                ]
                metric_len = LineString(projected).length
                if metric_len < 25:
                    continue

                path_class, confidence = _classify_path(color, width)
                if geo.georef_mode == "fallback_bbox":
                    confidence = max(0.1, confidence - 0.25)
                features.append(
                    {
                        "geometry": LineString(lon_lat_coords),
                        "properties": {
                            "council": council,
                            "edition_year": edition_year,
                            "source_pdf": pdf_path.name,
                            "source_page": page_idx + 1,
                            "extract_version": EXTRACT_VERSION,
                            "georef_mode": geo.georef_mode,
                            "stroke_width": width,
                            "stroke_color": (
                                ",".join(f"{v:.3f}" for v in color) if color is not None else None
                            ),
                            "path_class": path_class,
                            "confidence": confidence,
                            "length_m": metric_len,
                        },
                    }
                )
                page_count += 1
        page_summary.append(
            {"page": page_idx + 1, "georef": True, "mode": geo.georef_mode, "features": page_count}
        )

    return features, {"pdf": pdf_path.name, "council": council, "pages": page_summary}


def run_extraction() -> tuple[Path, int]:
    sources = load_data_sources()
    maps = sources.get("yourmove_council_maps", {}).get("metro_pdfs", [])
    bbox = load_bbox()
    raw_dir = Path(DATA_DIR) / "council_maps" / "raw"
    processed_dir = Path(DATA_DIR) / "council_maps" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, Any]] = []
    total = 0
    combined_frames: list[gpd.GeoDataFrame] = []

    for entry in maps:
        council = entry["council"]
        year = int(entry.get("edition_year", 0))
        pdf_path = raw_dir / f"{council}_{year}.pdf"
        if not pdf_path.exists():
            print(f"Missing PDF for {council}: {pdf_path}")
            continue

        print(f"Extracting vectors from {pdf_path.name}")
        features, meta = extract_pdf_vectors(
            pdf_path,
            council,
            year,
            bbox,
            entry.get("fallback_bbox"),
        )
        manifest.append(meta)
        if not features:
            print(f"No extracted features for {council}")
            continue

        gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
        gdf = gdf[gdf["confidence"] >= 0.3].copy()
        if len(gdf) == 0:
            continue

        out_path = processed_dir / f"{council}_overlay.geojson"
        gdf.to_file(out_path, driver="GeoJSON")
        print(f"Saved {len(gdf)} extracted features to {out_path}")
        total += len(gdf)
        combined_frames.append(gdf)

    if combined_frames:
        combined = gpd.GeoDataFrame(
            pd_concat([frame for frame in combined_frames]), crs="EPSG:4326"
        )
        combined.to_file(processed_dir / "metro_council_overlay.geojson", driver="GeoJSON")

    with open(processed_dir / "extraction_manifest.json", "w", encoding="utf-8") as f:
        json.dump({"extract_version": EXTRACT_VERSION, "items": manifest}, f, indent=2)
    return processed_dir, total


def pd_concat(frames: list[gpd.GeoDataFrame]):
    import pandas as pd

    return pd.concat(frames, ignore_index=True)


def main():
    print("=== Extracting council bike paths from PDFs ===")
    processed_dir, total = run_extraction()
    print(f"Processed directory: {processed_dir}")
    print(f"Total extracted features: {total}")


if __name__ == "__main__":
    main()
