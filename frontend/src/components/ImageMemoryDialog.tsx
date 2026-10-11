import type { ImageReadiness } from '../types'

interface Props {
  readiness: ImageReadiness
  loading: boolean
  onRescan: () => void
  onFullQuality: () => void
  onLightning: () => void
  onCancel: () => void
}

export function ImageMemoryDialog({
  readiness,
  loading,
  onRescan,
  onFullQuality,
  onLightning,
  onCancel,
}: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/50 px-4">
      <div
        className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl space-y-5"
        role="dialog"
        aria-modal="true"
        aria-labelledby="memory-dialog-title"
      >
        <div>
          <h2 id="memory-dialog-title" className="text-lg font-semibold text-gray-900">
            Free some memory, or choose a render mode
          </h2>
          <p className="mt-2 text-sm text-gray-600">
            Full-quality rendering is fastest with at least{' '}
            <span className="font-semibold">{readiness.recommended_gb} GB available</span>.
            This Mac currently has{' '}
            <span className="font-semibold text-amber-700">{readiness.available_gb} GB</span>.
            Nothing will be closed automatically.
          </p>
        </div>

        <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            Top memory users (approximate)
          </p>
          <ol className="mt-2 space-y-1.5">
            {readiness.top_consumers.map(consumer => (
              <li key={consumer.name} className="flex justify-between text-sm text-gray-700">
                <span>{consumer.name}</span>
                <span className="font-medium">{consumer.memory_gb} GB</span>
              </li>
            ))}
            {readiness.top_consumers.length === 0 && (
              <li className="text-sm text-gray-500">
                Process details are unavailable in this environment.
              </li>
            )}
          </ol>
        </div>

        <div className="space-y-2">
          <button
            onClick={onRescan}
            disabled={loading}
            className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? 'Scanning…' : 'I freed memory — rescan'}
          </button>
          <button
            onClick={onLightning}
            disabled={loading}
            className="w-full rounded-lg border border-purple-300 bg-purple-50 px-4 py-2.5 text-sm font-medium text-purple-800 hover:bg-purple-100 disabled:opacity-50"
          >
            Run Lightning mode (faster draft quality)
          </button>
          <button
            onClick={onFullQuality}
            disabled={loading}
            className="w-full rounded-lg border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm font-medium text-amber-900 hover:bg-amber-100 disabled:opacity-50"
          >
            Run full quality anyway (may be slow)
          </button>
          <button
            onClick={onCancel}
            disabled={loading}
            className="w-full px-4 py-2 text-sm text-gray-500 hover:text-gray-800 disabled:opacity-50"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}
