import type { Post, PostStatus } from '../types'

interface Props {
  post: Post
  activity: string | null
}

const steps = [
  'Brief & questions',
  'Draft & improve',
  'Prepare scene',
  'Generate image',
  'Ready to post',
]

function activeStep(status: PostStatus): number {
  if (status === 'clarifying') return 0
  if (status === 'needs_input' || status === 'drafting') return 1
  if (status === 'locked') return 2
  if (status === 'image_queued' || status === 'image_failed') return 3
  return 4
}

export function JourneyProgress({ post, activity }: Props) {
  const current = activeStep(post.status)
  const progress = `${(current / (steps.length - 1)) * 100}%`

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm" aria-label="Post progress">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Your progress</p>
          <p className="mt-1 text-sm font-medium text-gray-800">
            Step {current + 1} of {steps.length}: {steps[current]}
          </p>
        </div>
        {activity && (
          <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
            {activity}
          </span>
        )}
      </div>

      <div className="relative">
        <div className="absolute left-3 right-3 top-3 h-1 rounded bg-gray-200" />
        <div
          className="absolute left-3 top-3 h-1 rounded bg-blue-500 transition-all duration-500"
          style={{ width: `calc(${progress} - ${current === steps.length - 1 ? '1.5rem' : '0rem'})` }}
        />
        <ol className="relative grid grid-cols-5 gap-2">
          {steps.map((step, index) => {
            const complete = index < current || (current === steps.length - 1 && index === current)
            const active = index === current && !complete
            return (
              <li key={step} className="text-center">
                <span
                  className={`mx-auto flex h-7 w-7 items-center justify-center rounded-full border-2 text-xs font-semibold ${
                    complete
                      ? 'border-green-600 bg-green-600 text-white'
                      : active
                        ? 'border-blue-600 bg-white text-blue-700'
                        : 'border-gray-300 bg-white text-gray-400'
                  }`}
                >
                  {complete ? '✓' : index + 1}
                </span>
                <span className={`mt-2 block text-[11px] leading-tight ${
                  index === current ? 'font-semibold text-gray-900' : 'text-gray-500'
                }`}>
                  {step}
                </span>
              </li>
            )
          })}
        </ol>
      </div>
    </section>
  )
}
