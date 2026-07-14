import type { Post } from '../types'

interface Props {
  history: Post[]
  activeId: string | null
  onSelect: (post: Post) => void
  onNew: () => void
}

const STATUS_COLOR: Record<string, string> = {
  clarifying: 'text-gray-500',
  drafting: 'text-yellow-600',
  locked: 'text-blue-600',
  image_queued: 'text-blue-600',
  image_ready: 'text-green-600',
  image_failed: 'text-red-600',
  ready: 'text-green-700',
}

export function HistorySidebar({ history, activeId, onSelect, onNew }: Props) {
  return (
    <aside className="w-64 shrink-0 space-y-2">
      <button
        onClick={onNew}
        className="w-full rounded-lg border border-dashed border-gray-300 px-3 py-2 text-xs font-medium text-gray-600 hover:border-blue-300 hover:bg-blue-50"
      >
        + New post
      </button>
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 pt-2">
        History
      </p>
      {history.map(p => (
        <button
          key={p.id}
          onClick={() => onSelect(p)}
          className={`w-full text-left rounded-lg border px-3 py-2 text-xs hover:border-blue-300 hover:bg-blue-50 transition-colors ${
            activeId === p.id ? 'border-blue-400 bg-blue-50' : 'border-gray-200 bg-white'
          }`}
        >
          <div className="font-medium text-gray-800 truncate">
            {p.brief.slice(0, 60)}
          </div>
          <div className={`mt-0.5 capitalize ${STATUS_COLOR[p.status] ?? 'text-gray-500'}`}>
            {p.status.replace('_', ' ')}
          </div>
        </button>
      ))}
    </aside>
  )
}
