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
    <section className="post-panel post-panel--compact" aria-labelledby="feedback-heading">
      <p id="feedback-heading" className="post-panel__eyebrow">
        Feedback (saved, not yet auto-applied)
      </p>
      <div className="post-feedback-fields">
        <label className="sr-only" htmlFor="feedback-stage">Feedback stage</label>
        <select
          id="feedback-stage"
          value={stage}
          onChange={e => setStage(e.target.value)}
        >
          {STAGES.map(s => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
        <label className="sr-only" htmlFor="feedback-note">Feedback note</label>
        <input
          id="feedback-note"
          placeholder="What would you change?"
          value={note}
          onChange={e => setNote(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && submit()}
        />
        <button
          type="button"
          onClick={submit}
          disabled={!note.trim()}
          className="post-button post-button--secondary"
        >
          {sent ? 'Saved ✓' : 'Save'}
        </button>
      </div>
    </section>
  )
}
