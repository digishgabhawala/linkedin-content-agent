import { useEffect, useState } from 'react'
import type { Post } from '../types'

interface Props {
  post: Post
  onAnswer: (answer: string) => void
  loading: boolean
}

export function ClarifyChat({ post, onAnswer, loading }: Props) {
  const [answer, setAnswer] = useState('')
  const [elapsed, setElapsed] = useState(0)

  // Answering the LAST clarify question doesn't just save the answer -- it
  // synchronously runs the full draft -> judge -> recalibrate pipeline in
  // the same request, which routinely takes 60-120s+. With no feedback that
  // looks identical to "broken" (found live -- a user gave up mid-request
  // assuming it hung). This can't tell in advance which submission will be
  // the last one, so it just escalates the message the longer any answer
  // submission takes.
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
    if (!answer.trim() || loading) return
    onAnswer(answer.trim())
    setAnswer('')
  }

  function loadingMessage(): string | null {
    if (!loading) return null
    if (elapsed < 5) return 'Thinking…'
    if (elapsed < 15) return 'Still thinking — checking if we have enough detail yet…'
    return "Still working — if that was the last question, it's now writing and " +
      `scoring a full draft, which can take 1-2 minutes. (${elapsed}s)`
  }

  return (
    <section className="post-panel post-panel--conversation" aria-labelledby={`clarify-${post.id}-heading`}>
      <div>
        <p className="post-panel__eyebrow">Original brief</p>
        <p className="post-brief-copy">{post.brief}</p>
      </div>

      {post.pending_question && (
        <div className="post-question">
          <p className="post-question__label">One detail before we write</p>
          <h3 id={`clarify-${post.id}-heading`}>{post.pending_question}</h3>
        </div>
      )}

      <div className="post-field post-answer-field">
        <label htmlFor={`clarify-${post.id}-answer`}>Your answer</label>
        <input
          id={`clarify-${post.id}-answer`}
          placeholder="Your answer…"
          value={answer}
          onChange={e => setAnswer(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && submit()}
          disabled={loading}
        />
        <button
          type="button"
          onClick={submit}
          disabled={loading || !answer.trim()}
          className="post-button post-button--primary"
        >
          {loading ? 'Submitting…' : 'Answer question'}
        </button>
      </div>

      {loading && (
        <p className="post-live-status" role="status">{loadingMessage()}</p>
      )}
    </section>
  )
}
