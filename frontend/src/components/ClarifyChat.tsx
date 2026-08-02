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
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm space-y-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Brief</p>
        <p className="mt-1 text-sm text-gray-800">{post.brief}</p>
      </div>

      {post.pending_question && (
        <div className="rounded-lg bg-blue-50 border border-blue-100 p-3">
          <p className="text-sm text-blue-900">{post.pending_question}</p>
        </div>
      )}

      <div className="flex gap-2">
        <input
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
          placeholder="Your answer…"
          value={answer}
          onChange={e => setAnswer(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && submit()}
          disabled={loading}
        />
        <button
          onClick={submit}
          disabled={loading || !answer.trim()}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? '…' : 'Answer'}
        </button>
      </div>

      {loading && (
        <p className="text-xs text-gray-500 animate-pulse">{loadingMessage()}</p>
      )}
    </div>
  )
}
