import { useState, useCallback } from 'react'
import MapView from './components/MapView'
import RouteBuilder from './components/RouteBuilder'
import RoutePanel from './components/RoutePanel'
import { calculateRoute, type LatLon, type RouteResponse } from './api/client'

type RouteProfile = 'psp_priority' | 'balanced' | 'shortest';

function App() {
  const [origin, setOrigin] = useState<LatLon | null>(null)
  const [destination, setDestination] = useState<LatLon | null>(null)
  const [waypoints, setWaypoints] = useState<LatLon[]>([])
  const [route, setRoute] = useState<RouteResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [profile, setProfile] = useState<RouteProfile>('psp_priority')
  const [avoidBusyRoads, setAvoidBusyRoads] = useState(true)
  const [detourLimit, setDetourLimit] = useState(1.25)
  const [placingPoint, setPlacingPoint] = useState<'origin' | 'destination' | null>('origin')

  const handleMapClick = useCallback((latlng: LatLon) => {
    if (placingPoint === 'origin') {
      setOrigin(latlng)
      setPlacingPoint('destination')
    } else if (placingPoint === 'destination') {
      setDestination(latlng)
      setPlacingPoint(null)
    }
  }, [placingPoint])

  const handleCalculateRoute = useCallback(async () => {
    if (!origin || !destination) return

    setLoading(true)
    setError(null)

    const pspPriority = profile === 'psp_priority' ? 0.95 : profile === 'balanced' ? 0.6 : 0.1

    try {
      const result = await calculateRoute({
        origin,
        destination,
        waypoints,
        preferences: {
          psp_priority: pspPriority,
          avoid_busy_roads: avoidBusyRoads,
          max_detour_ratio: detourLimit,
        },
        alternatives: 1,
        format: 'geojson',
      })
      setRoute(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Route calculation failed')
    } finally {
      setLoading(false)
    }
  }, [origin, destination, waypoints, profile, avoidBusyRoads, detourLimit])

  const handleReset = useCallback(() => {
    setOrigin(null)
    setDestination(null)
    setWaypoints([])
    setRoute(null)
    setError(null)
    setPlacingPoint('origin')
  }, [])

  return (
    <div className="flex h-full w-full">
      {/* Sidebar */}
      <div className="w-96 h-full bg-white shadow-lg z-10 flex flex-col overflow-y-auto">
        {/* Header */}
        <div className="p-4 bg-emerald-600 text-white">
          <h1 className="text-xl font-bold">Perth PSP Router</h1>
          <p className="text-sm text-emerald-100">Plan cycling routes that maximise shared paths</p>
        </div>

        {/* Route builder controls */}
        <RouteBuilder
          origin={origin}
          destination={destination}
          waypoints={waypoints}
          profile={profile}
          avoidBusyRoads={avoidBusyRoads}
          detourLimit={detourLimit}
          placingPoint={placingPoint}
          loading={loading}
          onSetOrigin={setOrigin}
          onSetDestination={setDestination}
          onSetWaypoints={setWaypoints}
          onSetProfile={setProfile}
          onSetAvoidBusyRoads={setAvoidBusyRoads}
          onSetDetourLimit={setDetourLimit}
          onSetPlacingPoint={setPlacingPoint}
          onCalculateRoute={handleCalculateRoute}
          onReset={handleReset}
        />

        {/* Error display */}
        {error && (
          <div className="mx-4 mb-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm">
            {error}
          </div>
        )}

        {/* Route results */}
        {route && <RoutePanel route={route} />}

        {/* Attribution */}
        <div className="mt-auto p-3 text-xs text-gray-400 border-t">
          Data: OSM (ODbL) | DoT WA (CC BY 4.0) | MRWA (CC BY 4.0)
        </div>
      </div>

      {/* Map */}
      <div className="flex-1 h-full">
        <MapView
          origin={origin}
          destination={destination}
          waypoints={waypoints}
          route={route}
          placingPoint={placingPoint}
          onMapClick={handleMapClick}
        />
      </div>
    </div>
  )
}

export default App
