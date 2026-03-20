import { getGpxUrl, getGeoJsonUrl } from '../api/client'

interface ExportButtonsProps {
  routeId: string
}

export default function ExportButtons({ routeId }: ExportButtonsProps) {
  return (
    <div className="flex gap-2">
      <a
        href={getGpxUrl(routeId)}
        download
        className="flex-1 py-2 px-3 text-center text-sm font-medium rounded-lg border border-emerald-600 text-emerald-700 hover:bg-emerald-50 transition-colors"
      >
        Download GPX
      </a>
      <a
        href={getGeoJsonUrl(routeId)}
        download
        className="flex-1 py-2 px-3 text-center text-sm font-medium rounded-lg border border-blue-600 text-blue-700 hover:bg-blue-50 transition-colors"
      >
        Download GeoJSON
      </a>
    </div>
  )
}
