import { useEffect, useState } from 'react'
import type { Post } from '../types'

interface Props {
  post: Post
  onRetry: () => void
}

function elapsedLabel(startedAt: string | null): string {
  if (!startedAt) return ''
  const mins = Math.floor((Date.now() - new Date(startedAt).getTime()) / 60000)
  if (mins < 1) return 'just started'
  return `${mins} min ago`
}

export function ImageStatus({ post, onRetry }: Props) {
  const [, forceTick] = useState(0)

  // re-render every 30s so the elapsed-time label stays live while polling
  useEffect(() => {
    if (post.status !== 'image_queued') return
    const t = setInterval(() => forceTick(n => n + 1), 30000)
    return () => clearInterval(t)
  }, [post.status])

  if (post.status === 'image_queued') {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm space-y-2">
        <p className="text-sm font-medium text-gray-800">
          Rendering… (typically 15-30 min on this hardware)
        </p>
        <p className="text-xs text-gray-500">Started {elapsedLabel(post.image_started_at)}</p>
        {post.is_stalled && (
          <p className="rounded-lg bg-amber-50 border border-amber-100 p-2 text-xs text-amber-800">
            This is taking longer than {' '}
            <span className="font-medium">the usual stall timeout</span> — check ComfyUI is
            still running and hasn't errored out silently.
          </p>
        )}
      </div>
    )
  }

  if (post.status === 'image_failed') {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 shadow-sm space-y-3">
        <p className="text-sm font-medium text-red-900">Image generation failed</p>
        {post.image_job_error && (
          <pre className="whitespace-pre-wrap text-xs text-red-700">{post.image_job_error}</pre>
        )}
        <button
          onClick={onRetry}
          className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
        >
          Retry
        </button>
      </div>
    )
  }

  return null
}
