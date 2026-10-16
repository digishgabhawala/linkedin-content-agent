import type { Post } from '../types'

interface Props {
  history: Post[]
  activeId: string | null
  onSelect: (post: Post) => void
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

export function HistorySidebar({ history, activeId, onSelect }: Props) {
  return (
    <aside className="posts-history" aria-labelledby="post-history-heading">
      <div className="posts-history__heading">
        <div>
          <p className="posts-history__eyebrow">Workspace</p>
          <h3 id="post-history-heading">Recent posts</h3>
        </div>
        <span>{history.length}</span>
      </div>
      <div className="posts-history__list">
        {history.map(p => (
          <button
            type="button"
            key={p.id}
            onClick={() => onSelect(p)}
            aria-current={activeId === p.id ? 'true' : undefined}
            className="posts-history__item"
          >
            <span className="posts-history__brief">{p.brief.slice(0, 72)}</span>
            <span className={`posts-history__status capitalize ${STATUS_COLOR[p.status] ?? 'text-gray-500'}`}>
              {p.status.replace('_', ' ')}
            </span>
          </button>
        ))}
      </div>
    </aside>
  )
}
