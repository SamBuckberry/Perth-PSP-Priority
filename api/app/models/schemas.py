from pydantic import BaseModel, Field
from typing import Optional


class LatLon(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class RoutePreferences(BaseModel):
    psp_priority: float = Field(0.95, ge=0.0, le=1.0, description="PSP preference weight (0=none, 1=max)")
    avoid_busy_roads: bool = True
    max_detour_ratio: float = Field(1.2, ge=1.0, le=2.0, description="Max detour vs shortest route")


class RouteRequest(BaseModel):
    origin: LatLon
    destination: LatLon
    waypoints: list[LatLon] = Field(default_factory=list)
    preferences: RoutePreferences = Field(default_factory=RoutePreferences)
    alternatives: int = Field(1, ge=1, le=3)
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


class RouteResponse(BaseModel):
    route_id: str
    summary: RouteSummary
    warnings: list[RouteWarning] = Field(default_factory=list)
    segments: list[RouteSegment] = Field(default_factory=list)
    geometry: dict  # GeoJSON geometry
