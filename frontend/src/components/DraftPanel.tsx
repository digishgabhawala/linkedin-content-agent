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
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Draft v{post.draft_version}
        </p>
        <span className="text-xs text-gray-400">{post.post_text?.length ?? 0} chars</span>
      </div>

      <pre className="whitespace-pre-wrap font-sans text-sm text-gray-800 leading-relaxed">
        {post.post_text}
      </pre>

      <div className="flex gap-2">
        <input
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
          placeholder="Revision instruction, e.g. 'shorter hook, more punch'…"
          value={instruction}
          onChange={e => setInstruction(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && submitRegenerate()}
          disabled={loading}
        />
        <button
          onClick={submitRegenerate}
          disabled={loading || !instruction.trim()}
          className="rounded-lg bg-gray-700 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50 whitespace-nowrap"
        >
          Revise
        </button>
      </div>

      <div className="flex gap-2 pt-2 border-t border-gray-100">
        <button
          onClick={onRedraft}
          disabled={loading}
          className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          Start over
        </button>
        <button
          onClick={onLock}
          disabled={loading}
          className="ml-auto rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Lock this draft →
        </button>
      </div>
    </div>
  )
}
