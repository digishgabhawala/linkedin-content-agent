import type { Post } from '../types'

interface Props {
  post: Post
  onRetry: () => void
  loading: boolean
}

const STEP_LABELS: Record<string, string> = {
  category: 'Understanding your brief',
  clarify: 'Thinking of a clarifying question',
  draft: 'Writing a draft',
  rewrite: 'Rewriting the draft',
  judge: 'Scoring the draft',
  escalation: 'Working out what is missing',
  scene: 'Deriving the image scene',
}

/** The post's current queue step (text steps; the image step has its own card). */
export function StepStatus({ post, onRetry, loading }: Props) {
  const step = post.active_step
  if (step && step.name !== 'image') {
    const task = step.task
    const where = !task
      ? 'Submitted to the task queue…'
      : task.status === 'claimed'
        ? `Running on ${task.claimed_by ?? 'a worker'}${task.progress_message ? ` — ${task.progress_message}` : ''}`
        : 'Waiting for a worker (it may be busy rendering an image, or none is online)'
    return (
      <section className="post-status-card post-status-card--info" aria-live="polite">
        <span className="post-status-card__indicator" aria-hidden="true" />
        <div>
          <p>{STEP_LABELS[step.name] ?? step.name}…</p>
          <span>{where}</span>
        </div>
      </section>
    )
  }
  if (post.step_error && post.can_retry_step && post.status !== 'image_failed') {
    return (
      <section className="post-status-card post-status-card--danger" role="alert">
        <div>
          <p>The last step did not finish</p>
          <pre>{post.step_error}</pre>
        </div>
        <button
          type="button"
          onClick={onRetry}
          disabled={loading}
          className="post-button post-button--danger"
        >
          Retry step
        </button>
      </section>
    )
  }
  return null
}
