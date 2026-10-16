import { useEffect, useState } from 'react'
import { api } from '../api'
import type { PostDraft } from '../types'

interface Props {
  postId: string
  currentVersion: number
}

export function DraftHistory({ postId, currentVersion }: Props) {
  const [drafts, setDrafts] = useState<PostDraft[]>([])
  const [open, setOpen] = useState(false)

  useEffect(() => {
    api.getDrafts(postId).then(setDrafts).catch(() => {})
  }, [postId, currentVersion])

  if (drafts.length <= 1) return null

  return (
    <section className="post-panel post-panel--compact post-disclosure-panel">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="post-disclosure-toggle"
        aria-expanded={open}
      >
        <span>Draft history <span className="post-chip">{drafts.length}</span></span>
        <span aria-hidden="true">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div className="post-disclosure-panel__body">
          {[...drafts].reverse().map(d => (
            <div key={d.id} className="post-history-entry">
              <div className="post-history-entry__heading">
                <strong>
                  v{d.version} · {d.generated_by}
                  {d.version === currentVersion && (
                    <span className="post-chip">
                      current
                    </span>
                  )}
                </strong>
                {d.created_at && <span>{new Date(d.created_at).toLocaleTimeString()}</span>}
              </div>
              {d.user_instruction && (
                <p className="post-history-entry__instruction">“{d.user_instruction}”</p>
              )}
              <span className="post-history-entry__preview">
                {d.post_text}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
