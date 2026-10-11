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
      <div className="rounded-xl border border-blue-100 bg-blue-50 p-4" aria-live="polite">
        <p className="text-sm font-medium text-blue-900">{STEP_LABELS[step.name] ?? step.name}…</p>
        <p className="mt-1 text-xs text-blue-800">{where}</p>
      </div>
    )
  }
  if (post.step_error && post.can_retry_step && post.status !== 'image_failed') {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 space-y-2">
        <p className="text-sm font-medium text-red-900">The last step did not finish</p>
        <pre className="whitespace-pre-wrap text-xs text-red-700">{post.step_error}</pre>
        <button
          onClick={onRetry}
          disabled={loading}
          className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
        >
          Retry step
        </button>
      </div>
    )
  }
  return null
}
