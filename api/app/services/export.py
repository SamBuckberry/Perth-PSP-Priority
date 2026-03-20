import json
import gpxpy
import gpxpy.gpx

from app.models.schemas import RouteResponse


def route_to_gpx(route: RouteResponse) -> str:
    """Convert a route response to GPX track format."""
    gpx = gpxpy.gpx.GPX()
    gpx.name = f"Perth PSP Route {route.route_id}"
    gpx.description = (
        f"PSP share: {route.summary.psp_share:.0%} | "
        f"Distance: {route.summary.distance_m / 1000:.1f} km"
    )

    track = gpxpy.gpx.GPXTrack()
    track.name = gpx.name
    gpx.tracks.append(track)

    segment = gpxpy.gpx.GPXTrackSegment()
    track.segments.append(segment)

    coords = route.geometry.get("coordinates", [])
    for coord in coords:
        lon, lat = coord[0], coord[1]
        ele = coord[2] if len(coord) > 2 else None
        segment.points.append(gpxpy.gpx.GPXTrackPoint(lat, lon, elevation=ele))

    return gpx.to_xml()


def route_to_geojson(route: RouteResponse) -> dict:
    """Convert a route response to GeoJSON Feature."""
    return {
        "type": "Feature",
        "properties": {
            "route_id": route.route_id,
            "distance_m": route.summary.distance_m,
            "psp_share": route.summary.psp_share,
            "on_road_m": route.summary.on_road_m,
            "busy_road_m": route.summary.busy_road_m,
            "crossings_signalised": route.summary.crossings.signalised,
            "crossings_unsignalised": route.summary.crossings.unsignalised,
        },
        "geometry": route.geometry,
    }
