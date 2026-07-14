import { useState } from 'react'

interface Props {
  onSubmit: (stage: string, note: string) => void
}

const STAGES = [
  { value: 'draft', label: 'Draft text' },
  { value: 'image_scene', label: 'Image scene' },
  { value: 'final', label: 'Final post' },
]

/** Capture-only -- this feedback is stored (see feedback_service.py) but not
 * yet fed back into any prompt. Just building the habit of recording it. */
export function FeedbackForm({ onSubmit }: Props) {
  const [stage, setStage] = useState('draft')
  const [note, setNote] = useState('')
  const [sent, setSent] = useState(false)

  function submit() {
    if (!note.trim()) return
    onSubmit(stage, note.trim())
    setNote('')
    setSent(true)
    setTimeout(() => setSent(false), 2000)
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
        Feedback (saved, not yet auto-applied)
      </p>
      <div className="flex gap-2">
        <select
          value={stage}
          onChange={e => setStage(e.target.value)}
          className="rounded-lg border border-gray-300 px-2 py-1.5 text-xs"
        >
          {STAGES.map(s => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
        <input
          className="flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-xs focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
          placeholder="What would you change?"
          value={note}
          onChange={e => setNote(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && submit()}
        />
        <button
          onClick={submit}
          disabled={!note.trim()}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          {sent ? 'Saved ✓' : 'Save'}
        </button>
      </div>
    </div>
  )
}
