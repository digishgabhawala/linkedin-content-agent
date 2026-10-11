import type { LocalRendererStatus } from '../types'

interface Props {
  status: LocalRendererStatus | null
}

export function RendererStatusBadge({ status }: Props) {
  const online = status?.online === true
  const label = status === null ? 'Checking…' : online ? 'Online' : 'Offline'

  return (
    <div className="text-right" title={status?.message ?? 'Checking the local worker and ComfyUI'}>
      <div className="flex items-center justify-end gap-2 text-sm font-medium text-gray-800">
        <span
          className={`h-2.5 w-2.5 rounded-full ${
            status === null ? 'bg-gray-400' : online ? 'bg-green-500' : 'bg-red-500'
          }`}
        />
        Local renderer: {label}
      </div>
      <p className="mt-0.5 text-xs text-gray-500">
        {status?.message ?? 'Checking worker and ComfyUI…'}
      </p>
    </div>
  )
}
