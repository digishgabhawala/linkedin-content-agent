import { useEffect, useState } from 'react'
import type { Post } from '../types'

interface Props {
  post: Post
  onRetry: () => void
}

function elapsedLabel(startedAt: string | null): string {
  if (!startedAt) return ''
  const mins = Math.max(0, Math.floor((Date.now() - new Date(startedAt).getTime()) / 60000))
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
    const rendering = post.image_queue_status === 'claimed'
    const waiting = post.image_queue_status === 'queued'
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm space-y-2">
        <p className="text-sm font-medium text-gray-800">
          {rendering
            ? 'Rendering in progress — a worker has claimed this image'
            : waiting
              ? 'Waiting for an image worker — rendering has not started yet'
              : 'Checking whether an image worker has started…'}
        </p>
        <p className="text-xs text-gray-500">
          {rendering && post.image_claimed_at
            ? `Worker started ${elapsedLabel(post.image_claimed_at)}`
            : `Queued ${elapsedLabel(post.image_started_at)}`}
        </p>
        {rendering && (
          <div className="h-2 overflow-hidden rounded-full bg-blue-100" aria-label="Image rendering in progress">
            <div className="h-full w-1/3 animate-pulse rounded-full bg-blue-600" />
          </div>
        )}
        {waiting && (
          <p className="rounded-lg border border-amber-100 bg-amber-50 p-2 text-xs text-amber-800">
            {post.is_queue_delayed
              ? 'This task has been waiting longer than usual. Check that the local image worker is online.'
              : 'The task is safely stored in the hosted queue. Start the local image worker to begin rendering.'}
          </p>
        )}
        {rendering && post.is_stalled && (
          <p className="rounded-lg bg-amber-50 border border-amber-100 p-2 text-xs text-amber-800">
            Rendering has exceeded the usual runtime — check that ComfyUI is still making
            progress and hasn't errored out silently.
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
