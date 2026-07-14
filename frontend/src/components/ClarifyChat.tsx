import { useState } from 'react'
import type { Post } from '../types'

interface Props {
  post: Post
  onAnswer: (answer: string) => void
  loading: boolean
}

export function ClarifyChat({ post, onAnswer, loading }: Props) {
  const [answer, setAnswer] = useState('')

  function submit() {
    if (!answer.trim() || loading) return
    onAnswer(answer.trim())
    setAnswer('')
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
    </div>
  )
}
