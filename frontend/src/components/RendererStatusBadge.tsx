import type { RendererStatus, RendererWorker } from '../types'

interface Props {
  status: RendererStatus | null
}

function ago(iso: string | null): string {
  if (!iso) return ''
  const mins = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000))
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  return `${Math.floor(mins / 60)} h ago`
}

function workerLine(w: RendererWorker): string {
  const parts = [`${w.name}: ${w.state}`]
  if (w.details.comfyui?.state) parts.push(`ComfyUI ${w.details.comfyui.state}`)
  if (w.details.memory?.available_gb !== undefined) {
    parts.push(`${w.details.memory.available_gb} GB free`)
  }
  return parts.join(' · ')
}

export function RendererStatusBadge({ status }: Props) {
  const label = status === null
    ? 'Checking…'
    : !status.reachable
      ? 'Unreachable'
      : !status.online
        ? 'Offline'
        : status.busy_count === status.online_count
          ? 'Busy'
          : 'Online'
  const dot = status === null
    ? 'bg-gray-400'
    : !status.reachable
      ? 'bg-amber-500'
      : !status.online
        ? 'bg-red-500'
        : label === 'Busy'
          ? 'bg-blue-500'
          : 'bg-green-500'
  const detail = status === null
    ? 'Checking the task queue…'
    : status.last_seen_at
      ? `${status.message} — last seen ${ago(status.last_seen_at)}`
      : status.message
  const title = status?.workers.length
    ? status.workers.map(workerLine).join('\n')
    : detail

  return (
    <div className="text-right" title={title}>
      <div className="flex items-center justify-end gap-2 text-sm font-medium text-gray-800">
        <span className={`h-2.5 w-2.5 rounded-full ${dot}`} />
        Image worker: {label}
      </div>
      <p className="mt-0.5 text-xs text-gray-500">{detail}</p>
    </div>
  )
}
