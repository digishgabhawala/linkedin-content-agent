import { useEffect, useState } from 'react'
import type { Post } from '../types'

interface Props {
  post: Post
  onRetry: () => void
  onRetryLightning: () => void
}

function elapsedLabel(startedAt: string | null): string {
  if (!startedAt) return ''
  const started = new Date(startedAt).getTime()
  if (!Number.isFinite(started)) return ''
  const mins = Math.max(0, Math.floor((Date.now() - started) / 60000))
  if (mins < 1) return 'just started'
  return `${mins} min ago`
}

const STAGE_LABELS: Record<string, string> = {
  claimed: 'Claimed by a worker',
  preparing: 'Preparing',
  rendering: 'Rendering',
  uploading: 'Uploading',
  starting_comfyui: 'Starting ComfyUI',
  freeing_memory: 'Freeing memory from the text model',
}

// Older workers never report a stage -- a claimed task is still rendering.
function stageLabel(stage: string | null): string {
  return (stage && STAGE_LABELS[stage]) || 'Rendering'
}

export function ImageStatus({ post, onRetry, onRetryLightning }: Props) {
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
      <section className="post-panel post-panel--image-status" aria-live="polite">
        <p className="post-image-status__heading">
          {rendering
            ? `${stageLabel(post.image_progress_stage)}${post.image_worker_id ? ` on ${post.image_worker_id}` : ''}`
            : waiting
              ? 'Waiting for an image worker — rendering has not started yet'
              : 'Checking whether an image worker has started…'}
        </p>
        {rendering && post.image_progress_message && (
          <p className="post-image-status__message">{post.image_progress_message}</p>
        )}
        <p className="post-panel__meta">
          {rendering && post.image_claimed_at
            ? `Worker started ${elapsedLabel(post.image_claimed_at)}`
            : `Queued ${elapsedLabel(post.image_started_at)}`}
        </p>
        {rendering && (
          <div className="post-render-progress" aria-label="Image rendering in progress">
            <div />
          </div>
        )}
        {waiting && (
          <p className="post-message post-message--warning">
            {post.is_queue_delayed
              ? 'This task has been waiting longer than usual. Check that the local image worker is online.'
              : 'The task is safely stored in the hosted queue. Start the local image worker to begin rendering.'}
          </p>
        )}
        {rendering && post.is_worker_lost && (
          <p className="post-message post-message--danger">
            The worker rendering this image stopped reporting
            {post.image_progress_updated_at ? ` (last update ${elapsedLabel(post.image_progress_updated_at)})` : ''}.
            The task stays in the queue and will be picked up again when an image worker is running.
          </p>
        )}
        {rendering && !post.is_worker_lost && post.is_stalled && (
          <p className="post-message post-message--warning">
            {post.image_progress_updated_at
              ? 'Rendering is taking longer than usual. The worker is still reporting in, so it is probably just slow — full-quality renders can take over an hour on a busy Mac.'
              : "Rendering is taking longer than usual. This worker doesn't report progress, so we can't confirm it is still running — check it directly."}
          </p>
        )}
      </section>
    )
  }

  if (post.status === 'image_failed') {
    return (
      <section className="post-panel post-panel--danger" role="alert">
        {post.image_failure_kind === 'corrupt_output' ? (
          <>
            <h3 className="post-attention-heading">The image came back blank</h3>
            <p className="post-attention-copy">
              This usually happens when the Mac is low on memory or ComfyUI has been running a
              long time. Retry renders again with a new seed.
            </p>
          </>
        ) : post.image_failure_kind === 'insufficient_memory' ? (
          <>
            <h3 className="post-attention-heading">Not enough free memory for full quality</h3>
            <p className="post-attention-copy">
              The image worker refused this render rather than risk a blank image. Free some
              memory and retry, or render in Lightning mode instead.
            </p>
          </>
        ) : (
          <h3 className="post-attention-heading">Image generation failed</h3>
        )}
        {post.image_job_error && (
          <pre className="post-error-detail">{post.image_job_error}</pre>
        )}
        <div className="post-actions">
          {post.image_failure_kind === 'insufficient_memory' && (
            <button
              onClick={onRetryLightning}
              className="post-button post-button--primary"
            >
              Retry with Lightning
            </button>
          )}
          <button
            onClick={onRetry}
            className="post-button post-button--danger"
          >
            Retry
          </button>
        </div>
      </section>
    )
  }

  return null
}
