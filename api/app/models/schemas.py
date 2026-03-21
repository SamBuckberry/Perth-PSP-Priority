from pydantic import BaseModel, Field
from typing import Optional


class LatLon(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class RoutePreferences(BaseModel):
    psp_priority: float = Field(0.95, ge=0.0, le=1.0, description="PSP preference weight (0=none, 1=max)")
    psp_weight: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Bike-path weighting slider value (0-100)"
    )
    routing_mode: str = Field(
        "hard_psp_anchor",
        pattern="^(weighted|hard_psp_anchor)$",
        description="Routing strategy mode",
    )
    avoid_busy_roads: bool = True
    max_detour_ratio: float = Field(1.25, ge=1.0, le=2.0, description="Max detour vs shortest route")
    phase_search_radius_m: int = Field(
        2500,
        ge=200,
        le=10000,
        description="Anchor search radius for dedicated corridors in hard mode",
    )
    phase_candidate_limit: int = Field(
        3,
        ge=1,
        le=8,
        description="Candidate corridor anchors to evaluate in hard mode",
    )
    preferred_councils: list[str] = Field(
        default_factory=list,
        description="Preferred council overlays to favour for PSP anchor selection",
    )


class RouteRequest(BaseModel):
    origin: LatLon
    destination: LatLon
    waypoints: list[LatLon] = Field(default_factory=list)
    preferences: RoutePreferences = Field(default_factory=RoutePreferences)
    alternatives: int = Field(1, ge=1, le=8)
    format: str = Field("geojson", pattern="^(geojson|gpx)$")


class CrossingSummary(BaseModel):
    signalised: int = 0
    unsignalised: int = 0


class RouteSummary(BaseModel):
    distance_m: float
    estimated_time_min: float
    psp_share: float = Field(..., ge=0.0, le=1.0)
    on_road_m: float
    busy_road_m: float
    crossings: CrossingSummary


class RouteWarning(BaseModel):
    type: str
    message: str


class RouteSegment(BaseModel):
    facility_class: str
    distance_m: float
    coordinates: list[list[float]]
    source_hint: Optional[str] = None


class RouteResponse(BaseModel):
    route_id: str
    summary: RouteSummary
    warnings: list[RouteWarning] = Field(default_factory=list)
    segments: list[RouteSegment] = Field(default_factory=list)
    geometry: dict  # GeoJSON geometry
