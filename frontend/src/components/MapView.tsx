import { useEffect } from 'react'
import { MapContainer, TileLayer, Marker, Polyline, useMapEvents, useMap } from 'react-leaflet'
import L from 'leaflet'
import type { LatLon, RouteResponse } from '../api/client'

// Custom marker icons
const originIcon = new L.DivIcon({
  className: '',
  html: '<div style="background:#059669;color:white;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:14px;border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.3)">A</div>',
  iconSize: [28, 28],
  iconAnchor: [14, 14],
})

const destinationIcon = new L.DivIcon({
  className: '',
  html: '<div style="background:#dc2626;color:white;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:14px;border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.3)">B</div>',
  iconSize: [28, 28],
  iconAnchor: [14, 14],
})

// Facility class colors
const FACILITY_COLORS: Record<string, string> = {
  PSP: '#059669',                    // emerald-600 (bold green)
  OFFROAD_SHARED_PATH_HQ: '#10b981', // emerald-500
  OFFROAD_SHARED_PATH: '#34d399',    // emerald-400
  CYCLE_TRACK_PROTECTED: '#3b82f6',  // blue-500
  CYCLE_LANE_PAINTED: '#f59e0b',     // amber-500
  QUIET_STREET: '#8b5cf6',           // violet-500
  BUSY_ROAD_NO_INFRA: '#ef4444',     // red-500
}

// Perth CBD center
const PERTH_CENTER: [number, number] = [-31.9505, 115.8605]

interface MapViewProps {
  origin: LatLon | null
  destination: LatLon | null
  waypoints: LatLon[]
  route: RouteResponse | null
  placingPoint: 'origin' | 'destination' | null
  onMapClick: (latlng: LatLon) => void
}

function MapClickHandler({ onMapClick, placingPoint }: {
  onMapClick: (latlng: LatLon) => void
  placingPoint: 'origin' | 'destination' | null
}) {
  const map = useMapEvents({
    click(e) {
      if (placingPoint) {
        onMapClick({ lat: e.latlng.lat, lon: e.latlng.lng })
      }
    },
  })

  // Change cursor based on placing mode
  useEffect(() => {
    const container = map.getContainer()
    container.style.cursor = placingPoint ? 'crosshair' : ''
    return () => { container.style.cursor = '' }
  }, [map, placingPoint])

  return null
}

function RouteSegments({ route }: { route: RouteResponse }) {
  return (
    <>
      {route.segments.map((segment, i) => {
        const positions = segment.coordinates.map(
          (c) => [c[1], c[0]] as [number, number]
        )
        const color = FACILITY_COLORS[segment.facility_class] || '#6b7280'

        return (
          <Polyline
            key={i}
            positions={positions}
            pathOptions={{
              color,
              weight: segment.facility_class === 'PSP' ? 6 : 4,
              opacity: 0.85,
            }}
          />
        )
      })}
    </>
  )
}

function FitBounds({ origin, destination }: { origin: LatLon; destination: LatLon }) {
  const map = useMap()
  useEffect(() => {
    const bounds = L.latLngBounds(
      [origin.lat, origin.lon],
      [destination.lat, destination.lon],
    )
    map.fitBounds(bounds, { padding: [50, 50] })
  }, [map, origin, destination])
  return null
}

export default function MapView({
  origin,
  destination,
  waypoints,
  route,
  placingPoint,
  onMapClick,
}: MapViewProps) {
  return (
    <MapContainer
      center={PERTH_CENTER}
      zoom={12}
      className="h-full w-full"
      zoomControl={true}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      <MapClickHandler onMapClick={onMapClick} placingPoint={placingPoint} />

      {/* Origin marker */}
      {origin && (
        <Marker position={[origin.lat, origin.lon]} icon={originIcon} />
      )}

      {/* Destination marker */}
      {destination && (
        <Marker position={[destination.lat, destination.lon]} icon={destinationIcon} />
      )}

      {/* Route segments (color-coded by facility class) */}
      {route && <RouteSegments route={route} />}

      {/* Fit map to route bounds */}
      {origin && destination && (
        <FitBounds origin={origin} destination={destination} />
      )}
    </MapContainer>
  )
}
