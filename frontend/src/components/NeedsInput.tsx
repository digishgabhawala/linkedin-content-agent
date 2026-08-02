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
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 shadow-sm space-y-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">
        Needs your input
      </p>
      <p className="whitespace-pre-wrap text-sm text-amber-900">{post.escalation_reason}</p>

      {post.post_text && (
        <details className="text-sm text-gray-700">
          <summary className="cursor-pointer text-xs font-medium text-gray-500">
            Current best draft
          </summary>
          <pre className="mt-2 whitespace-pre-wrap font-sans text-sm leading-relaxed">
            {post.post_text}
          </pre>
        </details>
      )}

      <textarea
        value={info}
        onChange={e => setInfo(e.target.value)}
        placeholder="Add the detail requested above..."
        rows={3}
        className="w-full rounded-lg border border-gray-300 p-2 text-sm"
      />
      <div className="flex gap-3">
        <button
          onClick={submit}
          disabled={loading || !info.trim()}
          className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
        >
          Submit and retry
        </button>
        <button
          onClick={onAcceptDraft}
          disabled={loading}
          className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          Accept current draft as-is
        </button>
      </div>

      {loading && (
        <p className="text-xs text-gray-500 animate-pulse">
          Writing and scoring a fresh draft — this can take 1-2 minutes. ({elapsed}s)
        </p>
      )}
    </div>
  )
}
