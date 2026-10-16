import { useState } from 'react'
import type { Post, PillarScore } from '../types'

interface Props {
  post: Post
}

const GATE_THRESHOLD = 9.0
const RECALIBRATION_THRESHOLD = 6.5

const PILLAR_LABELS: Record<string, string> = {
  factual_integrity: 'Factual integrity',
  voice_authenticity: 'Voice authenticity',
  hook: 'Hook',
  structure: 'Structure',
  cta: 'CTA',
  length_fit: 'Length fit',
  character_consistency: 'Character consistency',
  topic_resonance: 'Topic resonance',
  profile_fit: 'Profile fit',
  market_timeliness: 'Market timeliness',
}

function scoreColor(score: number, threshold: number): string {
  if (score >= threshold) return 'post-score--success'
  if (score >= threshold - 2) return 'post-score--warning'
  return 'post-score--danger'
}

function Row({ pillar, entry, threshold }: { pillar: string; entry: PillarScore; threshold: number }) {
  return (
    <div className={`post-score ${scoreColor(entry.score, threshold)}`}>
      <div className="post-score__heading">
        <span>{PILLAR_LABELS[pillar] ?? pillar}</span>
        <span>{entry.score.toFixed(1)}/10</span>
      </div>
      <p>{entry.reason}</p>
    </div>
  )
}

export function PillarScores({ post }: Props) {
  const [open, setOpen] = useState(false)
  const hasScores = Object.keys(post.pillar_scores ?? {}).length > 0

  if (!hasScores) return null

  return (
    <section className="post-panel post-panel--compact post-disclosure-panel">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="post-disclosure-toggle"
        aria-expanded={open}
      >
        <span>
          Quality scores
          {post.category && <span className="post-chip">{post.category.replace(/_/g, ' ')}</span>}
          {post.weighted_score != null && (
            <span className="post-disclosure-toggle__score">{post.weighted_score.toFixed(1)}/10</span>
          )}
        </span>
        <span aria-hidden="true">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div className="post-disclosure-panel__body">
          <div>
            <p className="post-section-caption">Gates (must clear {GATE_THRESHOLD}/10)</p>
            <div className="post-score-list">
              {Object.entries(post.gate_scores).map(([pillar, entry]) => (
                <Row key={pillar} pillar={pillar} entry={entry} threshold={GATE_THRESHOLD} />
              ))}
            </div>
          </div>
          <div>
            <p className="post-section-caption">
              Optimization pillars (target {RECALIBRATION_THRESHOLD}/10)
            </p>
            <div className="post-score-list">
              {Object.entries(post.pillar_scores).map(([pillar, entry]) => (
                <Row key={pillar} pillar={pillar} entry={entry} threshold={RECALIBRATION_THRESHOLD} />
              ))}
            </div>
          </div>
          {post.recalibration_count > 1 && (
            <p className="post-field__hint">
              Went through {post.recalibration_count} automatic recalibration passes.
            </p>
          )}
        </div>
      )}
    </section>
  )
}
