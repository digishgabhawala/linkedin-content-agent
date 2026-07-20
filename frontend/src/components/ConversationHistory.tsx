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
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <button
        onClick={() => setOpen(o => !o)}
        className="text-xs font-semibold uppercase tracking-wide text-gray-500"
      >
        Conversation history ({answered.length}) {open ? '▲' : '▼'}
      </button>
      {open && (
        <div className="mt-3 space-y-3">
          <div className="rounded-lg border border-gray-100 p-3">
            <p className="text-xs font-medium text-gray-500">Original brief</p>
            <p className="mt-1 whitespace-pre-wrap text-xs text-gray-600">{post.brief}</p>
          </div>
          {answered.map((t, i) => (
            <div key={i} className="rounded-lg border border-gray-100 p-3">
              <p className="text-xs font-medium text-gray-500">Q: {t.question}</p>
              <p className="mt-1 whitespace-pre-wrap text-xs text-gray-600">A: {t.answer}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
