import type { LatLon } from '../api/client'

type RouteProfile = 'psp_priority' | 'balanced' | 'shortest';

interface RouteBuilderProps {
  origin: LatLon | null
  destination: LatLon | null
  waypoints: LatLon[]
  profile: RouteProfile
  avoidBusyRoads: boolean
  detourLimit: number
  placingPoint: 'origin' | 'destination' | null
  loading: boolean
  onSetOrigin: (v: LatLon | null) => void
  onSetDestination: (v: LatLon | null) => void
  onSetWaypoints: (v: LatLon[]) => void
  onSetProfile: (v: RouteProfile) => void
  onSetAvoidBusyRoads: (v: boolean) => void
  onSetDetourLimit: (v: number) => void
  onSetPlacingPoint: (v: 'origin' | 'destination' | null) => void
  onCalculateRoute: () => void
  onReset: () => void
}

function formatLatLon(ll: LatLon | null): string {
  if (!ll) return 'Click map to set'
  return `${ll.lat.toFixed(5)}, ${ll.lon.toFixed(5)}`
}

export default function RouteBuilder({
  origin,
  destination,
  profile,
  avoidBusyRoads,
  detourLimit,
  placingPoint,
  loading,
  onSetProfile,
  onSetAvoidBusyRoads,
  onSetDetourLimit,
  onSetPlacingPoint,
  onCalculateRoute,
  onReset,
}: RouteBuilderProps) {
  const canCalculate = origin !== null && destination !== null && !loading

  return (
    <div className="p-4 space-y-4">
      {/* Origin / Destination */}
      <div className="space-y-2">
        <div
          className={`flex items-center gap-2 p-3 rounded-lg border-2 cursor-pointer transition-colors ${
            placingPoint === 'origin' ? 'border-emerald-500 bg-emerald-50' : 'border-gray-200 hover:border-gray-300'
          }`}
          onClick={() => onSetPlacingPoint('origin')}
        >
          <div className="w-7 h-7 rounded-full bg-emerald-600 text-white flex items-center justify-center text-sm font-bold flex-shrink-0">
            A
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs text-gray-500">From</div>
            <div className="text-sm truncate">
              {origin ? formatLatLon(origin) : 'Click map to set start'}
            </div>
          </div>
        </div>

        <div
          className={`flex items-center gap-2 p-3 rounded-lg border-2 cursor-pointer transition-colors ${
            placingPoint === 'destination' ? 'border-red-500 bg-red-50' : 'border-gray-200 hover:border-gray-300'
          }`}
          onClick={() => onSetPlacingPoint('destination')}
        >
          <div className="w-7 h-7 rounded-full bg-red-600 text-white flex items-center justify-center text-sm font-bold flex-shrink-0">
            B
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs text-gray-500">To</div>
            <div className="text-sm truncate">
              {destination ? formatLatLon(destination) : 'Click map to set end'}
            </div>
          </div>
        </div>
      </div>

      {/* Route Profile */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Route Profile</label>
        <div className="grid grid-cols-3 gap-1 bg-gray-100 rounded-lg p-1">
          {([
            { key: 'psp_priority' as RouteProfile, label: 'PSP Priority', desc: 'Max shared paths' },
            { key: 'balanced' as RouteProfile, label: 'Balanced', desc: 'Mix of paths & roads' },
            { key: 'shortest' as RouteProfile, label: 'Shortest', desc: 'Minimum distance' },
          ]).map((p) => (
            <button
              key={p.key}
              className={`px-2 py-2 rounded-md text-xs font-medium transition-colors ${
                profile === p.key
                  ? 'bg-white shadow text-emerald-700'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
              onClick={() => onSetProfile(p.key)}
              title={p.desc}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Avoid busy roads toggle */}
      <div className="flex items-center justify-between">
        <label className="text-sm text-gray-700">Avoid busy roads</label>
        <button
          className={`relative w-11 h-6 rounded-full transition-colors ${
            avoidBusyRoads ? 'bg-emerald-600' : 'bg-gray-300'
          }`}
          onClick={() => onSetAvoidBusyRoads(!avoidBusyRoads)}
        >
          <span
            className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
              avoidBusyRoads ? 'translate-x-5' : ''
            }`}
          />
        </button>
      </div>

      {/* Detour limit slider */}
      <div>
        <div className="flex justify-between items-center mb-1">
          <label className="text-sm text-gray-700">Detour limit</label>
          <span className="text-sm text-gray-500">{Math.round((detourLimit - 1) * 100)}%</span>
        </div>
        <input
          type="range"
          min="1.05"
          max="1.5"
          step="0.05"
          value={detourLimit}
          onChange={(e) => onSetDetourLimit(parseFloat(e.target.value))}
          className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-emerald-600"
        />
        <div className="flex justify-between text-xs text-gray-400 mt-1">
          <span>5%</span>
          <span>50%</span>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex gap-2">
        <button
          className={`flex-1 py-3 rounded-lg font-medium text-sm transition-colors ${
            canCalculate
              ? 'bg-emerald-600 text-white hover:bg-emerald-700'
              : 'bg-gray-200 text-gray-400 cursor-not-allowed'
          }`}
          disabled={!canCalculate}
          onClick={onCalculateRoute}
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Calculating...
            </span>
          ) : (
            'Calculate Route'
          )}
        </button>
        <button
          className="px-4 py-3 rounded-lg font-medium text-sm border border-gray-300 text-gray-600 hover:bg-gray-50 transition-colors"
          onClick={onReset}
        >
          Reset
        </button>
      </div>
    </div>
  )
}
