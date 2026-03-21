import httpx
from typing import Any, Optional
from math import cos, radians, sqrt
import json
from pathlib import Path

from app.config import settings
from app.models.schemas import LatLon, RoutePreferences


CUSTOM_AREAS_FILE = Path("../data/export/areas/graphhopper_custom_areas.geojson")
WAY_PRIORITY_FILE = Path("../data/export/psp_way_priority.json")
PSP_NETWORK_FILE = Path("../data/export/psp_network.geojson")
COUNCIL_OVERLAY_FILE = Path("../data/export/council_overlay.geojson")
_WAY_PRIORITY_CACHE: Optional[dict[str, dict]] = None
_ANCHOR_CACHE: Optional[list[dict[str, Any]]] = None
_COUNCIL_OPTIONS_CACHE: Optional[list[str]] = None
DEDICATED_CLASSES = {"cycleway", "path", "track"}


def _load_way_priority_map() -> dict[str, dict]:
    global _WAY_PRIORITY_CACHE
    if _WAY_PRIORITY_CACHE is not None:
        return _WAY_PRIORITY_CACHE
    if not WAY_PRIORITY_FILE.exists():
        _WAY_PRIORITY_CACHE = {}
        return _WAY_PRIORITY_CACHE
    try:
        payload = json.loads(WAY_PRIORITY_FILE.read_text(encoding="utf-8"))
        _WAY_PRIORITY_CACHE = {
            str(item["osm_way_id"]): item for item in payload.get("items", []) if "osm_way_id" in item
        }
    except Exception:
        _WAY_PRIORITY_CACHE = {}
    return _WAY_PRIORITY_CACHE


def _has_custom_area(area_id: str) -> bool:
    if not CUSTOM_AREAS_FILE.exists():
        return False
    try:
        payload = json.loads(CUSTOM_AREAS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return False
    for feature in payload.get("features", []):
        if feature.get("id") == area_id:
            return True
        if feature.get("properties", {}).get("id") == area_id:
            return True
    return False


def _iter_linestring_coords(geometry: dict[str, Any]) -> list[list[float]]:
    geom_type = geometry.get("type")
    if geom_type == "LineString":
        return [geometry.get("coordinates", [])]
    if geom_type == "MultiLineString":
        return geometry.get("coordinates", [])
    return []


def _sample_line_points(line: list[list[float]]) -> list[list[float]]:
    if len(line) < 2:
        return []
    sampled: list[list[float]] = [line[0], line[-1]]
    if len(line) > 3:
        sampled.append(line[len(line) // 2])
    step = max(8, len(line) // 12)
    for idx in range(step, len(line) - 1, step):
        sampled.append(line[idx])
    return sampled


def _load_anchor_candidates() -> list[dict[str, Any]]:
    global _ANCHOR_CACHE, _COUNCIL_OPTIONS_CACHE
    if _ANCHOR_CACHE is not None:
        return _ANCHOR_CACHE

    anchors: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str]] = set()
    councils: set[str] = set()

    if PSP_NETWORK_FILE.exists():
        try:
            payload = json.loads(PSP_NETWORK_FILE.read_text(encoding="utf-8"))
            for feature in payload.get("features", []):
                props = feature.get("properties", {})
                source = str(props.get("psp_source") or "psp")
                for line in _iter_linestring_coords(feature.get("geometry", {})):
                    for coord in _sample_line_points(line):
                        if len(coord) < 2:
                            continue
                        lon = float(coord[0])
                        lat = float(coord[1])
                        key = (round(lat * 1e5), round(lon * 1e5), source)
                        if key in seen:
                            continue
                        seen.add(key)
                        anchors.append(
                            {
                                "point": LatLon(lat=lat, lon=lon),
                                "council": None,
                                "is_council": False,
                                "source": source,
                            }
                        )
        except Exception:
            pass

    if COUNCIL_OVERLAY_FILE.exists():
        try:
            payload = json.loads(COUNCIL_OVERLAY_FILE.read_text(encoding="utf-8"))
            for feature in payload.get("features", []):
                props = feature.get("properties", {})
                council = str(props.get("council") or "").strip()
                if not council:
                    continue
                councils.add(council)
                for line in _iter_linestring_coords(feature.get("geometry", {})):
                    for coord in _sample_line_points(line):
                        if len(coord) < 2:
                            continue
                        lon = float(coord[0])
                        lat = float(coord[1])
                        key = (round(lat * 1e5), round(lon * 1e5), f"council:{council}")
                        if key in seen:
                            continue
                        seen.add(key)
                        anchors.append(
                            {
                                "point": LatLon(lat=lat, lon=lon),
                                "council": council,
                                "is_council": True,
                                "source": "council_pdf",
                            }
                        )
        except Exception:
            pass

    _ANCHOR_CACHE = anchors
    _COUNCIL_OPTIONS_CACHE = sorted(councils)
    return _ANCHOR_CACHE


def get_council_options() -> list[str]:
    _load_anchor_candidates()
    return _COUNCIL_OPTIONS_CACHE or []


def _nearest_anchor_candidates(
    point: LatLon,
    limit: int,
    radius_m: int,
    preferred_councils: list[str],
) -> list[dict[str, Any]]:
    candidates = _load_anchor_candidates()
    if not candidates:
        return []

    preferred = {name.strip().lower() for name in preferred_councils if name.strip()}
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for candidate in candidates:
        distance_m = _distance_m(point, candidate["point"])
        council_name = str(candidate.get("council") or "").lower()
        if preferred:
            if council_name in preferred:
                rank = 0
            elif candidate.get("is_council"):
                rank = 2
            else:
                rank = 1
        elif candidate.get("is_council"):
            rank = 1
        else:
            rank = 0
        scored.append((distance_m, rank, candidate))

    scored.sort(key=lambda item: (item[1], item[0]))
    within_radius = [item for item in scored if item[0] <= radius_m]
    pool = within_radius if within_radius else scored
    return [item[2] for item in pool[: max(1, limit)]]


def _normalise_psp_priority(preferences: RoutePreferences) -> float:
    if preferences.psp_weight is None:
        return preferences.psp_priority
    return max(0.0, min(1.0, preferences.psp_weight / 100.0))


def _build_custom_model(preferences: RoutePreferences, mode: str = "weighted") -> dict[str, Any]:
    """Build a GraphHopper custom model based on user preferences."""
    psp_priority = _normalise_psp_priority(preferences)
    psp_boost = 2.0 + (psp_priority * 8.0)
    path_boost = 1.6 + (psp_priority * 5.0)
    busy_penalty = 0.2 if preferences.avoid_busy_roads else 0.6
    distance_influence = 35 + int((1.25 - preferences.max_detour_ratio) * 40)
    distance_influence = max(20, min(55, distance_influence))

    if mode == "approach":
        # Phase 1: join dedicated network quickly but safely.
        psp_boost = 14.0 + (psp_priority * 14.0)
        path_boost = 10.0 + (psp_priority * 10.0)
        busy_penalty = 0.05 if preferences.avoid_busy_roads else 0.2
        distance_influence = 18
    elif mode == "corridor":
        # Phase 2: strongly retain dedicated path usage.
        psp_boost = 20.0 + (psp_priority * 24.0)
        path_boost = 14.0 + (psp_priority * 18.0)
        busy_penalty = 0.02
        distance_influence = 5
    elif mode == "egress":
        # Phase 3: once leaving corridor, minimise road distance to destination.
        psp_boost = 1.6
        path_boost = 1.4
        busy_penalty = 0.2 if preferences.avoid_busy_roads else 0.45
        distance_influence = 95

    priority: list[dict[str, str]] = [
        {"if": "true", "multiply_by": "1.0"},
        {"if": "road_class == CYCLEWAY", "multiply_by": f"{psp_boost:.2f}"},
        {
            "if": "road_class == PATH || road_class == TRACK",
            "multiply_by": f"{path_boost:.2f}",
        },
        {"if": "road_class == FOOTWAY", "multiply_by": f"{(path_boost - 1.2):.2f}"},
        {
            "if": "road_class == PRIMARY || road_class == SECONDARY || road_class == TRUNK || road_class == MOTORWAY",
            "multiply_by": f"{busy_penalty:.2f}",
        },
        {"if": "road_environment == FERRY", "multiply_by": "0.10"},
    ]

    # Area signals are loaded from WA-informed ETL exports.
    if _has_custom_area("psp_corridor"):
        priority.insert(1, {"if": "in_psp_corridor", "multiply_by": f"{(psp_boost + 3):.2f}"})
    if _has_custom_area("offroad_corridor"):
        priority.insert(2, {"if": "in_offroad_corridor", "multiply_by": f"{(path_boost + 1.5):.2f}"})

    return {
        "priority": priority,
        "speed": [
            {
                "if": "true",
                "limit_to": "16",
            },
            {
                "if": "road_class == CYCLEWAY || road_class == PATH || road_class == TRACK",
                "limit_to": "23",
            },
        ],
        "distance_influence": distance_influence,
    }


def _detail_value(details: list[list[Any]], index: int):
    for start_idx, end_idx, value in details:
        if start_idx <= index <= end_idx:
            return value
    return None


def _is_dedicated_segment(road_class: Any, way_id_raw: Any, way_map: dict[str, dict]) -> bool:
    road_class_norm = str(road_class).lower()
    if road_class_norm == "cycleway":
        return True
    if road_class_norm in ("path", "track"):
        if way_id_raw is None:
            return True
        way_id = str(int(way_id_raw))
        way_info = way_map.get(way_id)
        if not way_info:
            return True
        sources = way_info.get("psp_sources", [])
        if any(str(src).startswith("council_pdf") for src in sources):
            return True
        return bool(way_info.get("psp_flag")) or int(way_info.get("priority_rank", 0)) >= 70
    return False


def _extract_anchor_points(
    path: dict[str, Any], way_map: dict[str, dict]
) -> Optional[tuple[LatLon, LatLon]]:
    coords = path.get("points", {}).get("coordinates", [])
    if len(coords) < 6:
        return None
    details = path.get("details", {})
    road_details = details.get("road_class", [])
    way_details = details.get("osm_way_id", [])
    dedicated_idx: list[int] = []
    for start_idx, end_idx, road_class in road_details:
        mid_idx = (start_idx + end_idx) // 2
        way_id_raw = _detail_value(way_details, mid_idx)
        if _is_dedicated_segment(road_class, way_id_raw, way_map):
            dedicated_idx.extend([start_idx, end_idx])

    if not dedicated_idx:
        return None
    first_idx = max(1, min(dedicated_idx))
    last_idx = min(len(coords) - 2, max(dedicated_idx))
    if last_idx - first_idx < 3:
        return None
    entry = LatLon(lat=coords[first_idx][1], lon=coords[first_idx][0])
    exit_ = LatLon(lat=coords[last_idx][1], lon=coords[last_idx][0])
    return entry, exit_


def _shift_and_append_details(
    destination: list[list[Any]], source: list[list[Any]], offset: int, last_end: int
) -> int:
    for start_idx, end_idx, value in source:
        start = start_idx + offset
        end = end_idx + offset
        if destination and destination[-1][2] == value and destination[-1][1] >= (start - 1):
            destination[-1][1] = max(destination[-1][1], end)
        else:
            destination.append([start, end, value])
        last_end = max(last_end, end)
    return last_end


def _estimate_path_metrics(path: dict[str, Any], way_map: dict[str, dict]) -> dict[str, float]:
    coords = path.get("points", {}).get("coordinates", [])
    details = path.get("details", {})
    road_details = details.get("road_class", [])
    way_details = details.get("osm_way_id", [])
    dedicated_distance = 0.0
    on_road_distance = 0.0
    busy_road_distance = 0.0
    total_distance = path.get("distance", 0.0)

    for start_idx, end_idx, road_class in road_details:
        seg_coords = coords[start_idx : end_idx + 1]
        if len(seg_coords) < 2:
            continue
        seg_distance = 0.0
        for i in range(1, len(seg_coords)):
            seg_distance += _distance_m(
                LatLon(lat=seg_coords[i - 1][1], lon=seg_coords[i - 1][0]),
                LatLon(lat=seg_coords[i][1], lon=seg_coords[i][0]),
            )
        way_id_raw = _detail_value(way_details, (start_idx + end_idx) // 2)
        if _is_dedicated_segment(road_class, way_id_raw, way_map):
            dedicated_distance += seg_distance
        else:
            on_road_distance += seg_distance
            if str(road_class).lower() in {"primary", "secondary", "tertiary", "trunk", "motorway"}:
                busy_road_distance += seg_distance

    return {
        "total_m": total_distance,
        "dedicated_m": dedicated_distance,
        "on_road_m": on_road_distance,
        "busy_road_m": busy_road_distance,
    }


def _merge_staged_paths(
    approach: dict[str, Any], corridor: dict[str, Any], egress: dict[str, Any], way_map: dict[str, dict]
) -> dict[str, Any]:
    staged = [approach, corridor, egress]
    merged_coords: list[list[float]] = []
    merged_details: dict[str, list[list[Any]]] = {
        "road_class": [],
        "surface": [],
        "road_environment": [],
        "osm_way_id": [],
    }
    offset = 0
    for idx, path in enumerate(staged):
        coords = path.get("points", {}).get("coordinates", [])
        if not coords:
            continue
        if idx == 0:
            merged_coords.extend(coords)
        else:
            merged_coords.extend(coords[1:])
            offset -= 1
        for key in merged_details.keys():
            source = path.get("details", {}).get(key, [])
            _shift_and_append_details(merged_details[key], source, offset, 0)
        offset += len(coords)

    approach_metrics = _estimate_path_metrics(approach, way_map)
    corridor_metrics = _estimate_path_metrics(corridor, way_map)
    egress_metrics = _estimate_path_metrics(egress, way_map)
    corridor_retention = (
        corridor_metrics["dedicated_m"] / corridor_metrics["total_m"]
        if corridor_metrics["total_m"] > 0
        else 0.0
    )

    return {
        "distance": sum(path.get("distance", 0.0) for path in staged),
        "time": sum(path.get("time", 0.0) for path in staged),
        "points": {"type": "LineString", "coordinates": merged_coords},
        "details": merged_details,
        "phase_metrics": {
            "approach_on_road_m": approach_metrics["on_road_m"],
            "corridor_retention_ratio": corridor_retention,
            "egress_on_road_m": egress_metrics["on_road_m"],
            "busy_road_m": (
                approach_metrics["busy_road_m"]
                + corridor_metrics["busy_road_m"]
                + egress_metrics["busy_road_m"]
            ),
        },
    }


async def _query_graphhopper(points: list[LatLon], custom_model: dict[str, Any], alternatives: int = 1):
    params: dict[str, Any] = {
        "profile": "bike",
        "points_encoded": False,
        "instructions": True,
        "calc_points": True,
        "details": ["road_class", "surface", "road_environment", "osm_way_id"],
    }
    if alternatives > 1:
        params["algorithm"] = "alternative_route"
        params["alternative_route.max_paths"] = alternatives
    body = {
        "points": [[p.lon, p.lat] for p in points],
        "custom_model": custom_model,
        **params,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(f"{settings.GRAPHHOPPER_URL}/route", json=body)
        response.raise_for_status()
        return response.json()


async def _build_hard_anchor_routes(
    origin: LatLon,
    destination: LatLon,
    waypoints: list[LatLon],
    preferences: RoutePreferences,
    alternatives: int,
) -> dict[str, Any]:
    points = [origin] + waypoints + [destination]
    way_map = _load_way_priority_map()
    preferred_councils = preferences.preferred_councils
    base_limit = max(1, min(preferences.phase_candidate_limit, 5))
    candidate_limit = base_limit if preferred_councils else max(2, base_limit)
    origin_candidates = _nearest_anchor_candidates(
        origin,
        limit=candidate_limit,
        radius_m=preferences.phase_search_radius_m,
        preferred_councils=preferred_councils,
    )
    destination_candidates = _nearest_anchor_candidates(
        destination,
        limit=candidate_limit,
        radius_m=preferences.phase_search_radius_m,
        preferred_councils=preferred_councils,
    )

    staged_candidates: list[dict[str, Any]] = []
    for origin_anchor in origin_candidates:
        for destination_anchor in destination_candidates:
            entry = origin_anchor["point"]
            exit_ = destination_anchor["point"]
            approach_data = await _query_graphhopper(
                points=[origin, entry],
                custom_model=_build_custom_model(preferences, mode="approach"),
            )
            corridor_points = [entry] + waypoints + [exit_]
            corridor_data = await _query_graphhopper(
                points=corridor_points,
                custom_model=_build_custom_model(preferences, mode="corridor"),
            )
            egress_data = await _query_graphhopper(
                points=[exit_, destination],
                custom_model=_build_custom_model(preferences, mode="egress"),
            )
            if (
                not approach_data.get("paths")
                or not corridor_data.get("paths")
                or not egress_data.get("paths")
            ):
                continue
            merged = _merge_staged_paths(
                approach_data["paths"][0], corridor_data["paths"][0], egress_data["paths"][0], way_map
            )
            preferred = {name.lower() for name in preferred_councils}
            anchor_councils = {
                str(origin_anchor.get("council") or "").lower(),
                str(destination_anchor.get("council") or "").lower(),
            }
            matched_preferred = bool(preferred and any(c in preferred for c in anchor_councils))
            merged["phase_metrics"]["council_preference_miss"] = 0.0 if matched_preferred else 1.0
            merged["phase_metrics"]["anchor_source"] = (
                f"{origin_anchor.get('source','psp')}->{destination_anchor.get('source','psp')}"
            )
            staged_candidates.append(merged)

    if staged_candidates:
        staged_candidates = sorted(
            staged_candidates,
            key=lambda p: (
                float(p.get("phase_metrics", {}).get("council_preference_miss", 0.0)),
                float(p.get("phase_metrics", {}).get("busy_road_m", 1e9)),
                -float(p.get("phase_metrics", {}).get("corridor_retention_ratio", 0.0)),
                float(p.get("phase_metrics", {}).get("egress_on_road_m", 1e9)),
                float(p.get("phase_metrics", {}).get("approach_on_road_m", 1e9)),
                float(p.get("distance", 1e9)),
            ),
        )
        return {
            "paths": staged_candidates[: max(1, alternatives)],
            "_hard_anchor": True,
            "hints": {"message": "hard_psp_anchor deterministic mode used"},
        }

    base = await _query_graphhopper(
        points=points,
        custom_model=_build_custom_model(preferences, mode="weighted"),
        alternatives=max(1, alternatives),
    )
    base["_hard_anchor_unavailable"] = True
    return base


async def get_route(
    origin: LatLon,
    destination: LatLon,
    waypoints: list[LatLon],
    preferences: RoutePreferences,
    alternatives: int = 1,
) -> dict[str, Any]:
    """Query GraphHopper for a route with PSP-priority custom model."""
    points = [origin] + waypoints + [destination]
    try:
        if preferences.routing_mode == "hard_psp_anchor":
            return await _build_hard_anchor_routes(
                origin=origin,
                destination=destination,
                waypoints=waypoints,
                preferences=preferences,
                alternatives=alternatives,
            )
        return await _query_graphhopper(
            points=points,
            custom_model=_build_custom_model(preferences, mode="weighted"),
            alternatives=alternatives,
        )
    except Exception:
        return _build_fallback_route(origin=origin, destination=destination, points=points)


def _distance_m(a: LatLon, b: LatLon) -> float:
    """Approximate metre distance for short urban links."""
    mean_lat = radians((a.lat + b.lat) / 2.0)
    dx = (b.lon - a.lon) * 111320 * cos(mean_lat)
    dy = (b.lat - a.lat) * 110540
    return sqrt((dx * dx) + (dy * dy))


def _build_fallback_route(
    origin: LatLon, destination: LatLon, points: list[LatLon]
) -> dict[str, Any]:
    """Return a synthetic route when GraphHopper is unavailable locally."""
    coordinates = [[p.lon, p.lat] for p in points]
    total_distance_m = 0.0
    for i in range(1, len(points)):
        total_distance_m += _distance_m(points[i - 1], points[i])

    # Assume easy riding speed so the UI can show estimated duration.
    speed_m_per_s = 5.5
    total_time_ms = int((total_distance_m / speed_m_per_s) * 1000)

    return {
        "_fallback": True,
        "paths": [
            {
                "distance": total_distance_m,
                "time": total_time_ms,
                "points": {"type": "LineString", "coordinates": coordinates},
                "details": {
                    "road_class": [[0, max(1, len(coordinates) - 1), "CYCLEWAY"]]
                },
            }
        ],
        "hints": {
            "message": "GraphHopper unavailable; using a local fallback route for testing."
        },
    }
