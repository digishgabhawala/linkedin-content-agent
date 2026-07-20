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
  if (score >= threshold) return 'text-green-700 bg-green-50 border-green-100'
  if (score >= threshold - 2) return 'text-amber-700 bg-amber-50 border-amber-100'
  return 'text-red-700 bg-red-50 border-red-100'
}

function Row({ pillar, entry, threshold }: { pillar: string; entry: PillarScore; threshold: number }) {
  return (
    <div className={`rounded-lg border p-2 ${scoreColor(entry.score, threshold)}`}>
      <div className="flex items-center justify-between text-xs font-medium">
        <span>{PILLAR_LABELS[pillar] ?? pillar}</span>
        <span>{entry.score.toFixed(1)}/10</span>
      </div>
      <p className="mt-0.5 text-xs opacity-80">{entry.reason}</p>
    </div>
  )
}

export function PillarScores({ post }: Props) {
  const [open, setOpen] = useState(false)
  const hasScores = Object.keys(post.pillar_scores ?? {}).length > 0

  if (!hasScores) return null

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex w-full items-center justify-between text-xs font-semibold uppercase tracking-wide text-gray-500"
      >
        <span>
          Quality scores
          {post.category && <span className="ml-2 rounded bg-gray-100 px-1.5 py-0.5 normal-case text-gray-600">{post.category.replace(/_/g, ' ')}</span>}
          {post.weighted_score != null && (
            <span className="ml-2 normal-case text-gray-700">{post.weighted_score.toFixed(1)}/10</span>
          )}
        </span>
        <span>{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="mt-3 space-y-3">
          <div>
            <p className="mb-1 text-xs font-medium text-gray-500">Gates (must clear {GATE_THRESHOLD}/10)</p>
            <div className="space-y-1.5">
              {Object.entries(post.gate_scores).map(([pillar, entry]) => (
                <Row key={pillar} pillar={pillar} entry={entry} threshold={GATE_THRESHOLD} />
              ))}
            </div>
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-gray-500">
              Optimization pillars (target {RECALIBRATION_THRESHOLD}/10)
            </p>
            <div className="space-y-1.5">
              {Object.entries(post.pillar_scores).map(([pillar, entry]) => (
                <Row key={pillar} pillar={pillar} entry={entry} threshold={RECALIBRATION_THRESHOLD} />
              ))}
            </div>
          </div>
          {post.recalibration_count > 1 && (
            <p className="text-xs text-gray-500">
              Went through {post.recalibration_count} automatic recalibration passes.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
