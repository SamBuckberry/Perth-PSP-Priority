import hashlib
import json
import uuid
from datetime import datetime, timezone

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
from app.services.router_client import get_route

router = APIRouter(prefix="/v1", tags=["routing"])

# In-memory route cache (replace with Redis in production)
_route_cache: dict[str, RouteResponse] = {}


def _generate_route_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    short = uuid.uuid4().hex[:8]
    return f"r_{ts}_{short}"


def _parse_gh_response(gh_data: dict) -> RouteResponse:
    """Parse GraphHopper response into our route model."""
    route_id = _generate_route_id()

    paths = gh_data.get("paths", [])
    if not paths:
        raise HTTPException(status_code=404, detail="No route found")

    path = paths[0]
    distance_m = path.get("distance", 0)
    time_ms = path.get("time", 0)
    geometry = path.get("points", {})

    # Parse road_class details for PSP share calculation
    psp_distance = 0.0
    on_road_distance = 0.0
    busy_road_distance = 0.0
    segments: list[RouteSegment] = []

    road_class_details = []
    for detail in path.get("details", {}).get("road_class", []):
        start_idx, end_idx, road_class = detail
        road_class_details.append((start_idx, end_idx, road_class))

    coords = geometry.get("coordinates", [])
    for start_idx, end_idx, road_class in road_class_details:
        seg_coords = coords[start_idx : end_idx + 1]

        # Estimate segment distance from coordinates
        seg_distance = 0.0
        for i in range(1, len(seg_coords)):
            # Simple approximation using coordinate deltas
            dx = (seg_coords[i][0] - seg_coords[i - 1][0]) * 111320 * 0.848
            dy = (seg_coords[i][1] - seg_coords[i - 1][1]) * 110540
            seg_distance += (dx**2 + dy**2) ** 0.5

        # Map GraphHopper road_class to our facility_class
        if road_class in ("CYCLEWAY",):
            facility = "PSP"
            psp_distance += seg_distance
        elif road_class in ("PATH", "TRACK"):
            facility = "OFFROAD_SHARED_PATH"
        elif road_class in ("RESIDENTIAL", "LIVING_STREET"):
            facility = "QUIET_STREET"
        elif road_class in ("PRIMARY", "SECONDARY", "TERTIARY", "TRUNK", "MOTORWAY"):
            facility = "BUSY_ROAD_NO_INFRA"
            busy_road_distance += seg_distance
            on_road_distance += seg_distance
        else:
            facility = "QUIET_STREET"
            on_road_distance += seg_distance

        segments.append(
            RouteSegment(
                facility_class=facility,
                distance_m=seg_distance,
                coordinates=seg_coords,
            )
        )

    psp_share = psp_distance / distance_m if distance_m > 0 else 0.0

    summary = RouteSummary(
        distance_m=distance_m,
        estimated_time_min=time_ms / 60000,
        psp_share=min(psp_share, 1.0),
        on_road_m=on_road_distance,
        busy_road_m=busy_road_distance,
        crossings=CrossingSummary(signalised=0, unsignalised=0),
    )

    route = RouteResponse(
        route_id=route_id,
        summary=summary,
        warnings=[],
        segments=segments,
        geometry=geometry,
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
        alternatives=request.alternatives,
    )

    route = _parse_gh_response(gh_data)
    _route_cache[route.route_id] = route
    return route


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
