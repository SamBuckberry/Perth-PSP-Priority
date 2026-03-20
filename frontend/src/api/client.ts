const API_BASE = '/v1';

export interface LatLon {
  lat: number;
  lon: number;
}

export interface RoutePreferences {
  psp_priority: number;
  avoid_busy_roads: boolean;
  max_detour_ratio: number;
}

export interface RouteRequest {
  origin: LatLon;
  destination: LatLon;
  waypoints: LatLon[];
  preferences: RoutePreferences;
  alternatives: number;
  format: string;
}

export interface CrossingSummary {
  signalised: number;
  unsignalised: number;
}

export interface RouteSummary {
  distance_m: number;
  estimated_time_min: number;
  psp_share: number;
  on_road_m: number;
  busy_road_m: number;
  crossings: CrossingSummary;
}

export interface RouteSegment {
  facility_class: string;
  distance_m: number;
  coordinates: number[][];
}

export interface RouteWarning {
  type: string;
  message: string;
}

export interface RouteResponse {
  route_id: string;
  summary: RouteSummary;
  warnings: RouteWarning[];
  segments: RouteSegment[];
  geometry: GeoJSON.LineString;
}

export async function calculateRoute(request: RouteRequest): Promise<RouteResponse> {
  const response = await fetch(`${API_BASE}/route`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Route calculation failed: ${error}`);
  }

  return response.json();
}

export function getGpxUrl(routeId: string): string {
  return `${API_BASE}/route/${routeId}.gpx`;
}

export function getGeoJsonUrl(routeId: string): string {
  return `${API_BASE}/route/${routeId}.geojson`;
}
