import httpx
from typing import Any

from app.config import settings
from app.models.schemas import LatLon, RoutePreferences


def _build_custom_model(preferences: RoutePreferences) -> dict:
    """Build a GraphHopper custom model based on user preferences."""
    psp_boost = 1.0 + (preferences.psp_priority * 4.0)  # 1.0 to 5.0
    busy_penalty = 0.4 if preferences.avoid_busy_roads else 0.8

    return {
        "priority": [
            {
                "if": "road_class == CYCLEWAY",
                "multiply_by": str(psp_boost),
            },
            {
                "if": "road_environment == FERRY",
                "multiply_by": "0.1",
            },
        ],
        "speed": [
            {
                "if": "true",
                "limit_to": "25",
            }
        ],
        "distance_influence": 30 + int(preferences.psp_priority * 70),
    }


async def get_route(
    origin: LatLon,
    destination: LatLon,
    waypoints: list[LatLon],
    preferences: RoutePreferences,
    alternatives: int = 1,
) -> dict[str, Any]:
    """Query GraphHopper for a route with PSP-priority custom model."""
    points = [origin] + waypoints + [destination]

    params: dict[str, Any] = {
        "profile": "bike",
        "points_encoded": False,
        "instructions": True,
        "calc_points": True,
        "details": ["road_class", "surface", "road_environment"],
        "algorithm": "alternative_route" if alternatives > 1 else "",
        "alternative_route.max_paths": alternatives,
    }

    body = {
        "points": [[p.lon, p.lat] for p in points],
        "custom_model": _build_custom_model(preferences),
        **params,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{settings.GRAPHHOPPER_URL}/route",
            json=body,
        )
        response.raise_for_status()
        return response.json()
