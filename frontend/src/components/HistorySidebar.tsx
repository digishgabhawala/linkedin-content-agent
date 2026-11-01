import type { Post } from '../types'

interface Props {
  history: Post[]
  activeId: string | null
  archived: boolean
  onArchivedChange: (archived: boolean) => void
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

function autoArchiveNotice(value: string | null) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return `Archives automatically on ${date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })} unless edited`
}

export function HistorySidebar({ history, activeId, archived, onArchivedChange, onSelect }: Props) {
  return (
    <aside className="posts-history" aria-label={archived ? 'Archived posts' : 'Active posts'}>
      <div className="posts-history__heading">
        <div>
          <p className="posts-history__eyebrow">Workspace</p>
          <h3 id="post-history-heading">Recent posts</h3>
        </div>
        <span>{history.length}</span>
      </div>
      <div className="posts-history__switch" aria-label="Post history view">
        <button
          type="button"
          aria-pressed={!archived}
          onClick={() => onArchivedChange(false)}
        >
          Active
        </button>
        <button
          type="button"
          aria-pressed={archived}
          onClick={() => onArchivedChange(true)}
        >
          Archived
        </button>
      </div>
      <div className="posts-history__list">
        {history.length === 0 ? (
          <p className="posts-history__empty">No {archived ? 'archived' : 'active'} posts.</p>
        ) : history.map(p => {
          const notice = autoArchiveNotice(p.auto_archive_on)
          return (
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
              {notice && <span className="posts-history__notice">{notice}</span>}
            </button>
          )
        })}
      </div>
    </aside>
  )
}
