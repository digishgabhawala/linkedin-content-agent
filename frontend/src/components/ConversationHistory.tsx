import { useState } from 'react'
import type { Post } from '../types'

interface Props {
  post: Post
}

export function ConversationHistory({ post }: Props) {
  const [open, setOpen] = useState(false)
  const answered = post.clarify_transcript.filter(t => t.answer !== null)

  if (answered.length === 0) return null

  return (
    <section className="post-panel post-panel--compact post-disclosure-panel">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="post-disclosure-toggle"
        aria-expanded={open}
      >
        <span>Conversation history <span className="post-chip">{answered.length}</span></span>
        <span aria-hidden="true">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div className="post-disclosure-panel__body">
          <div className="post-history-entry">
            <p>Original brief</p>
            <span>{post.brief}</span>
          </div>
          {answered.map((t, i) => (
            <div key={i} className="post-history-entry">
              <p>Q: {t.question}</p>
              <span>A: {t.answer}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
