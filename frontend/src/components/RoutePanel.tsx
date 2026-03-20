import type { RouteResponse } from '../api/client'
import ExportButtons from './ExportButtons'

// Facility class display config
const FACILITY_DISPLAY: Record<string, { label: string; color: string }> = {
  PSP: { label: 'Principal Shared Path', color: '#059669' },
  OFFROAD_SHARED_PATH_HQ: { label: 'Quality Shared Path', color: '#10b981' },
  OFFROAD_SHARED_PATH: { label: 'Shared Path', color: '#34d399' },
  CYCLE_TRACK_PROTECTED: { label: 'Protected Cycle Track', color: '#3b82f6' },
  CYCLE_LANE_PAINTED: { label: 'Painted Cycle Lane', color: '#f59e0b' },
  QUIET_STREET: { label: 'Quiet Street', color: '#8b5cf6' },
  BUSY_ROAD_NO_INFRA: { label: 'Busy Road', color: '#ef4444' },
}

interface RoutePanelProps {
  route: RouteResponse
}

export default function RoutePanel({ route }: RoutePanelProps) {
  const { summary } = route
  const distKm = (summary.distance_m / 1000).toFixed(1)
  const timeMin = Math.round(summary.estimated_time_min)
  const pspPct = Math.round(summary.psp_share * 100)
  const onRoadKm = (summary.on_road_m / 1000).toFixed(1)
  const busyKm = (summary.busy_road_m / 1000).toFixed(1)

  // Aggregate segment distances by facility class
  const segmentsByClass: Record<string, number> = {}
  for (const seg of route.segments) {
    segmentsByClass[seg.facility_class] = (segmentsByClass[seg.facility_class] || 0) + seg.distance_m
  }

  return (
    <div className="p-4 border-t space-y-4">
      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="text-center">
          <div className="text-2xl font-bold text-gray-800">{distKm}</div>
          <div className="text-xs text-gray-500">km</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-gray-800">{timeMin}</div>
          <div className="text-xs text-gray-500">min</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-emerald-600">{pspPct}%</div>
          <div className="text-xs text-gray-500">PSP</div>
        </div>
      </div>

      {/* PSP share bar */}
      <div>
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>PSP Coverage</span>
          <span>{pspPct}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-3">
          <div
            className="bg-emerald-500 h-3 rounded-full transition-all"
            style={{ width: `${pspPct}%` }}
          />
        </div>
      </div>

      {/* Detail metrics */}
      <div className="space-y-1 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-500">On-road distance</span>
          <span className="text-gray-700">{onRoadKm} km</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Busy road exposure</span>
          <span className={`font-medium ${parseFloat(busyKm) > 0.5 ? 'text-red-600' : 'text-emerald-600'}`}>
            {busyKm} km
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Signalised crossings</span>
          <span className="text-gray-700">{summary.crossings.signalised}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Unsignalised crossings</span>
          <span className="text-gray-700">{summary.crossings.unsignalised}</span>
        </div>
      </div>

      {/* Segment breakdown */}
      <div>
        <h3 className="text-sm font-medium text-gray-700 mb-2">Route Breakdown</h3>
        <div className="space-y-1.5">
          {Object.entries(segmentsByClass)
            .sort(([, a], [, b]) => b - a)
            .map(([cls, dist]) => {
              const display = FACILITY_DISPLAY[cls] || { label: cls, color: '#6b7280' }
              const pct = Math.round((dist / summary.distance_m) * 100)
              return (
                <div key={cls} className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded-sm flex-shrink-0"
                    style={{ backgroundColor: display.color }}
                  />
                  <span className="text-xs text-gray-600 flex-1">{display.label}</span>
                  <span className="text-xs text-gray-500">{(dist / 1000).toFixed(1)} km</span>
                  <span className="text-xs text-gray-400 w-8 text-right">{pct}%</span>
                </div>
              )
            })}
        </div>
      </div>

      {/* Warnings */}
      {route.warnings.length > 0 && (
        <div className="space-y-2">
          {route.warnings.map((w, i) => (
            <div key={i} className="p-2 bg-amber-50 text-amber-800 rounded text-xs">
              {w.message}
            </div>
          ))}
        </div>
      )}

      {/* Export buttons */}
      <ExportButtons routeId={route.route_id} />
    </div>
  )
}
