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
    <section className="post-progress" aria-label="Post progress">
      <div className="post-progress__heading">
        <div>
          <p className="post-panel__eyebrow">Post journey</p>
          <p className="post-progress__current">
            Step {current + 1} of {steps.length}: {steps[current]}
          </p>
        </div>
        {activity && (
          <span className="post-progress__activity" role="status">
            {activity}
          </span>
        )}
      </div>

      <div className="post-progress__track">
        <div className="post-progress__rail" />
        <div
          className="post-progress__fill"
          style={{ width: `calc(${progress} - ${current === steps.length - 1 ? '1.5rem' : '0rem'})` }}
        />
        <ol className="post-progress__steps">
          {steps.map((step, index) => {
            const complete = index < current || (current === steps.length - 1 && index === current)
            const active = index === current && !complete
            return (
              <li key={step} className="post-progress__step">
                <span
                  className={`post-progress__marker ${
                    complete
                      ? 'post-progress__marker--complete'
                      : active
                        ? 'post-progress__marker--active'
                        : ''
                  }`}
                >
                  <span aria-hidden="true">{complete ? '✓' : index + 1}</span>
                  <span className="sr-only">{complete ? 'Complete' : `Step ${index + 1}`}</span>
                </span>
                <span className={`post-progress__label ${index === current ? 'post-progress__label--active' : ''}`}>
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
