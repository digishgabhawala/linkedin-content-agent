import { useEffect, useState } from 'react'
import type { Post } from '../types'

interface Props {
  post: Post
  onSubmitInfo: (info: string) => void
  onAcceptDraft: () => void
  loading: boolean
}

export function NeedsInput({ post, onSubmitInfo, onAcceptDraft, loading }: Props) {
  const [info, setInfo] = useState('')
  const [elapsed, setElapsed] = useState(0)

  // Submitting here always re-runs the full draft -> judge -> recalibrate
  // pipeline (unlike clarify, where only the final answer does) -- see the
  // matching note in ClarifyChat.tsx for why this needs explicit feedback.
  useEffect(() => {
    if (!loading) {
      setElapsed(0)
      return
    }
    const start = Date.now()
    const id = setInterval(() => setElapsed(Math.round((Date.now() - start) / 1000)), 1000)
    return () => clearInterval(id)
  }, [loading])

  function submit() {
    if (!info.trim()) return
    onSubmitInfo(info.trim())
    setInfo('')
  }

  return (
    <section className="post-panel post-panel--warning" aria-labelledby={`needs-input-${post.id}`}>
      <p className="post-panel__eyebrow post-panel__eyebrow--warning">
        Needs your input
      </p>
      <h3 id={`needs-input-${post.id}`} className="post-attention-heading">A real detail is missing</h3>
      <p className="post-attention-copy">{post.escalation_reason}</p>

      {post.post_text && (
        <details className="post-disclosure">
          <summary>
            Current best draft
          </summary>
          <pre className="post-copy post-copy--nested">
            {post.post_text}
          </pre>
        </details>
      )}

      <div className="post-field">
        <label htmlFor={`needs-input-${post.id}-detail`}>Additional detail</label>
        <textarea
          id={`needs-input-${post.id}-detail`}
          value={info}
          onChange={e => setInfo(e.target.value)}
          placeholder="Add the detail requested above…"
          rows={4}
        />
      </div>
      <div className="post-actions">
        <button
          type="button"
          onClick={submit}
          disabled={loading || !info.trim()}
          className="post-button post-button--warning"
        >
          Submit and retry
        </button>
        <button
          type="button"
          onClick={onAcceptDraft}
          disabled={loading}
          className="post-button post-button--secondary"
        >
          Accept current draft as-is
        </button>
      </div>

      {loading && (
        <p className="post-live-status" role="status">
          Writing and scoring a fresh draft — this can take 1-2 minutes. ({elapsed}s)
        </p>
      )}
    </section>
  )
}
