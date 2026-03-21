import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Response

from app.models.schemas import (
    CrossingSummary,
    RouteRequest,
    RouteResponse,
    RouteSegment,
    RouteSummary,
    RouteWarning,
)
from app.services.export import route_to_geojson, route_to_gpx
from app.services.router_client import get_council_options, get_route

router = APIRouter(prefix="/v1", tags=["routing"])

# In-memory route cache (replace with Redis in production)
_route_cache: dict[str, RouteResponse] = {}
WAY_PRIORITY_FILE = Path("../data/export/psp_way_priority.json")
_way_priority_cache: Optional[dict[str, dict]] = None


def _generate_route_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    short = uuid.uuid4().hex[:8]
    return f"r_{ts}_{short}"


def _load_way_priority_map() -> dict[str, dict]:
    global _way_priority_cache
    if _way_priority_cache is not None:
        return _way_priority_cache
    if not WAY_PRIORITY_FILE.exists():
        _way_priority_cache = {}
        return _way_priority_cache
    try:
        payload = json.loads(WAY_PRIORITY_FILE.read_text(encoding="utf-8"))
        _way_priority_cache = {
            item["osm_way_id"]: item for item in payload.get("items", []) if "osm_way_id" in item
        }
    except Exception:
        _way_priority_cache = {}
    return _way_priority_cache


def _detail_value(details: list[list], index: int):
    for start_idx, end_idx, value in details:
        if start_idx <= index <= end_idx:
            return value
    return None


def _segment_distance(seg_coords: list[list[float]]) -> float:
    seg_distance = 0.0
    for i in range(1, len(seg_coords)):
        dx = (seg_coords[i][0] - seg_coords[i - 1][0]) * 111320 * 0.848
        dy = (seg_coords[i][1] - seg_coords[i - 1][1]) * 110540
        seg_distance += (dx**2 + dy**2) ** 0.5
    return seg_distance


def _summarise_path(path: dict, way_priority_map: dict[str, dict]) -> dict:
    distance_m = path.get("distance", 0.0)
    time_ms = path.get("time", 0.0)
    geometry = path.get("points", {})
    coords = geometry.get("coordinates", [])
    details = path.get("details", {})
    road_details = details.get("road_class", [])
    way_details = details.get("osm_way_id", [])

    if not road_details and len(coords) >= 2:
        road_details = [[0, len(coords) - 1, "OTHER"]]

    psp_distance = 0.0
    dedicated_distance = 0.0
    on_road_distance = 0.0
    busy_road_distance = 0.0
    segments: list[RouteSegment] = []
    segment_is_dedicated: list[bool] = []
    segment_is_on_road: list[bool] = []

    for start_idx, end_idx, road_class in road_details:
        seg_coords = coords[start_idx : end_idx + 1]
        if len(seg_coords) < 2:
            continue
        seg_distance = _segment_distance(seg_coords)
        road_class_norm = str(road_class).lower()
        mid_idx = (start_idx + end_idx) // 2
        way_id_raw = _detail_value(way_details, mid_idx)
        way_id = str(int(way_id_raw)) if way_id_raw is not None else None
        way_info = way_priority_map.get(way_id) if way_id else None
        way_rank = int(way_info.get("priority_rank", 0)) if way_info else 0
        way_sources = way_info.get("psp_sources", []) if way_info else []
        has_council_signal = any(str(src).startswith("council_pdf") for src in way_sources)
        has_wa_signal = any(str(src) in ("mrwa_psp_nodes", "ltcn_primary") for src in way_sources)

        if has_council_signal or way_rank >= 120:
            facility = "PSP"
            psp_distance += seg_distance
            dedicated_distance += seg_distance
            segment_is_dedicated.append(True)
            segment_is_on_road.append(False)
        elif (way_info and way_info.get("psp_flag")) or way_rank >= 90 or road_class_norm == "cycleway":
            facility = "PSP"
            psp_distance += seg_distance
            dedicated_distance += seg_distance
            segment_is_dedicated.append(True)
            segment_is_on_road.append(False)
        elif road_class_norm in ("path", "track"):
            facility = "OFFROAD_SHARED_PATH_HQ"
            dedicated_distance += seg_distance
            if has_wa_signal or way_rank >= 90:
                psp_distance += seg_distance
                segment_is_dedicated.append(True)
            else:
                segment_is_dedicated.append(False)
            segment_is_on_road.append(False)
        elif road_class_norm == "footway":
            facility = "OFFROAD_SHARED_PATH"
            dedicated_distance += seg_distance
            segment_is_dedicated.append(False)
            segment_is_on_road.append(False)
        elif road_class_norm in ("residential", "living_street", "service"):
            facility = "QUIET_STREET"
            on_road_distance += seg_distance
            segment_is_dedicated.append(False)
            segment_is_on_road.append(True)
        elif road_class_norm in ("primary", "secondary", "tertiary", "trunk", "motorway"):
            facility = "BUSY_ROAD_NO_INFRA"
            busy_road_distance += seg_distance
            on_road_distance += seg_distance
            segment_is_dedicated.append(False)
            segment_is_on_road.append(True)
        elif road_class_norm in ("cycle_lane",):
            facility = "CYCLE_LANE_PAINTED"
            on_road_distance += seg_distance
            segment_is_dedicated.append(False)
            segment_is_on_road.append(True)
        else:
            facility = "QUIET_STREET"
            on_road_distance += seg_distance
            segment_is_dedicated.append(False)
            segment_is_on_road.append(True)

        segments.append(
            RouteSegment(
                facility_class=facility,
                distance_m=seg_distance,
                coordinates=seg_coords,
                source_hint=";".join(str(s) for s in way_sources[:3]) if way_sources else None,
            )
        )

    psp_share = psp_distance / distance_m if distance_m > 0 else 0.0
    dedicated_share = dedicated_distance / distance_m if distance_m > 0 else 0.0
    first_dedicated = next((i for i, v in enumerate(segment_is_dedicated) if v), None)
    last_dedicated = (
        len(segment_is_dedicated) - 1 - next(
            (i for i, v in enumerate(reversed(segment_is_dedicated)) if v), len(segment_is_dedicated)
        )
        if any(segment_is_dedicated)
        else None
    )
    approach_on_road = 0.0
    egress_on_road = 0.0
    corridor_dedicated = 0.0
    corridor_total = 0.0
    for idx, segment in enumerate(segments):
        if first_dedicated is None or last_dedicated is None:
            if segment_is_on_road[idx]:
                approach_on_road += segment.distance_m
            continue
        if idx < first_dedicated and segment_is_on_road[idx]:
            approach_on_road += segment.distance_m
        elif idx > last_dedicated and segment_is_on_road[idx]:
            egress_on_road += segment.distance_m
        elif first_dedicated <= idx <= last_dedicated:
            corridor_total += segment.distance_m
            if segment_is_dedicated[idx]:
                corridor_dedicated += segment.distance_m
    corridor_retention = corridor_dedicated / corridor_total if corridor_total > 0 else 0.0
    phase_metrics = path.get("phase_metrics", {})
    approach_on_road = float(phase_metrics.get("approach_on_road_m", approach_on_road))
    egress_on_road = float(phase_metrics.get("egress_on_road_m", egress_on_road))
    corridor_retention = float(phase_metrics.get("corridor_retention_ratio", corridor_retention))
    busy_road_distance = float(phase_metrics.get("busy_road_m", busy_road_distance))
    anchor_source = str(phase_metrics.get("anchor_source", ""))
    summary = RouteSummary(
        distance_m=distance_m,
        estimated_time_min=time_ms / 60000,
        psp_share=min(psp_share, 1.0),
        on_road_m=on_road_distance,
        busy_road_m=busy_road_distance,
        crossings=CrossingSummary(signalised=0, unsignalised=0),
    )
    return {
        "summary": summary,
        "segments": segments,
        "geometry": geometry,
        "distance_m": distance_m,
        "phase_metrics": {
            "approach_on_road_m": approach_on_road,
            "corridor_retention_ratio": corridor_retention,
            "egress_on_road_m": egress_on_road,
            "dedicated_share": dedicated_share,
            "anchor_source": anchor_source,
        },
    }


def _rank_routes(candidates: list[dict], max_detour_ratio: float, routing_mode: str) -> tuple[dict, bool]:
    shortest = min((c["distance_m"] for c in candidates), default=0.0)
    within_detour = [
        c for c in candidates if shortest <= 0 or c["distance_m"] <= (shortest * max_detour_ratio)
    ]
    pool = within_detour if within_detour else candidates
    if routing_mode == "hard_psp_anchor":
        selected = sorted(
            pool,
            key=lambda c: (
                c["phase_metrics"]["approach_on_road_m"],
                c["phase_metrics"]["egress_on_road_m"],
                -c["summary"].psp_share,
                -c["phase_metrics"]["corridor_retention_ratio"],
                -c["phase_metrics"]["dedicated_share"],
                c["summary"].busy_road_m,
                c["summary"].distance_m,
            ),
        )[0]
    else:
        selected = sorted(
            pool,
            key=lambda c: (
                -c["summary"].psp_share,
                c["summary"].busy_road_m,
                c["summary"].distance_m,
            ),
        )[0]
    return selected, bool(within_detour)


def _parse_gh_response(gh_data: dict, max_detour_ratio: float, routing_mode: str) -> RouteResponse:
    """Parse GraphHopper response into our route model."""
    route_id = _generate_route_id()

    paths = gh_data.get("paths", [])
    if not paths:
        raise HTTPException(status_code=404, detail="No route found")

    way_priority_map = _load_way_priority_map()
    candidates = [_summarise_path(path, way_priority_map) for path in paths]
    best, within_detour = _rank_routes(candidates, max_detour_ratio, routing_mode)

    warnings: list[RouteWarning] = []
    if not within_detour:
        warnings.append(
            RouteWarning(
                type="detour_cap_exceeded",
                message="No alternative satisfied the PSP detour cap, so the best available route was selected.",
            )
        )
    if gh_data.get("_fallback"):
        warnings.append(
            RouteWarning(
                type="fallback_routing",
                message="GraphHopper is not available, so a direct fallback route is shown for local testing.",
            )
        )
    if gh_data.get("_hard_anchor_unavailable"):
        warnings.append(
            RouteWarning(
                type="hard_anchor_unavailable",
                message="Hard PSP anchoring could not find a suitable corridor anchor, so weighted routing was used.",
            )
        )
    council_in_segments = any(
        segment.source_hint and "council_pdf" in segment.source_hint for segment in best["segments"]
    )
    council_in_anchor = "council" in str(best.get("phase_metrics", {}).get("anchor_source", ""))
    if not (council_in_segments or council_in_anchor):
        warnings.append(
            RouteWarning(
                type="council_overlay_not_used",
                message="No council PDF overlay signal was matched on this route; result relies on WA and OSM signals.",
            )
        )

    route = RouteResponse(
        route_id=route_id,
        summary=best["summary"],
        warnings=warnings,
        segments=best["segments"],
        geometry=best["geometry"],
    )
    return route


@router.post("/route", response_model=RouteResponse)
async def calculate_route(request: RouteRequest):
    """Calculate a PSP-priority cycling route."""
    gh_data = await get_route(
        origin=request.origin,
        destination=request.destination,
        waypoints=request.waypoints,
        preferences=request.preferences,
        alternatives=max(1, request.alternatives),
    )

    route = _parse_gh_response(
        gh_data, request.preferences.max_detour_ratio, request.preferences.routing_mode
    )
    _route_cache[route.route_id] = route
    return route


@router.get("/councils")
async def list_councils():
    """Return available council overlays that can guide hard PSP anchor selection."""
    return {"items": get_council_options()}


@router.get("/route/{route_id}.gpx")
async def get_route_gpx(route_id: str):
    """Download route as GPX file."""
    route = _route_cache.get(route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    gpx_xml = route_to_gpx(route)
    return Response(
        content=gpx_xml,
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f"attachment; filename={route_id}.gpx"},
    )


@router.get("/route/{route_id}.geojson")
async def get_route_geojson(route_id: str):
    """Download route as GeoJSON."""
    route = _route_cache.get(route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    geojson = route_to_geojson(route)
    return Response(
        content=json.dumps(geojson),
        media_type="application/geo+json",
        headers={"Content-Disposition": f"attachment; filename={route_id}.geojson"},
    )
