import { useState } from 'react'
import type { Post } from '../types'

interface Props {
  post: Post
  onRedraft: () => void
  onRegenerate: (instruction: string) => void
  onLock: () => void
  loading: boolean
}

export function DraftPanel({ post, onRedraft, onRegenerate, onLock, loading }: Props) {
  const [instruction, setInstruction] = useState('')

  function submitRegenerate() {
    if (!instruction.trim() || loading) return
    onRegenerate(instruction.trim())
    setInstruction('')
  }

  return (
    <section className="post-panel post-panel--draft" aria-labelledby={`draft-${post.id}-heading`}>
      <div className="post-panel__topline">
        <p id={`draft-${post.id}-heading`} className="post-panel__eyebrow">
          Draft v{post.draft_version}
        </p>
        <span className="post-panel__meta">{post.post_text?.length ?? 0} characters</span>
      </div>

      <pre className="post-copy">
        {post.post_text}
      </pre>

      <div className="post-field post-revision-field">
        <label htmlFor={`draft-${post.id}-revision`}>How should this draft change?</label>
        <input
          id={`draft-${post.id}-revision`}
          placeholder="Revision instruction, e.g. 'shorter hook, more punch'…"
          value={instruction}
          onChange={e => setInstruction(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && submitRegenerate()}
          disabled={loading}
        />
        <button
          type="button"
          onClick={submitRegenerate}
          disabled={loading || !instruction.trim()}
          className="post-button post-button--secondary"
        >
          Revise draft
        </button>
      </div>

      <div className="post-actions post-actions--separated">
        <button
          type="button"
          onClick={onRedraft}
          disabled={loading}
          className="post-button post-button--secondary"
        >
          Start over
        </button>
        <button
          type="button"
          onClick={onLock}
          disabled={loading}
          className="post-button post-button--primary post-actions__primary"
        >
          Lock this draft
        </button>
      </div>
    </section>
  )
}
