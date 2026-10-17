import { useState, type FormEvent } from 'react'
import type { Character } from '../types'

interface Props {
  onSubmit: (brief: string, characterId?: string) => void
  loading: boolean
  // The user's characters with a locked hero, newest first (the default).
  mascots: Character[]
}

export function BriefForm({ onSubmit, loading, mascots }: Props) {
  const [brief, setBrief] = useState('')
  const [choice, setChoice] = useState('')
  const mascot = mascots.some(c => c.character_id === choice)
    ? choice : mascots[0]?.character_id

  function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    if (!brief.trim() || loading) return
    onSubmit(brief.trim(), mascot)
  }

  return (
    <form className="post-form" onSubmit={submit}>
      <div className="post-panel__heading">
        <p className="post-panel__eyebrow">Start with the substance</p>
        <h3 id="new-post-heading">What did you work on?</h3>
        <p>
          Share the concrete change, decision, lesson, or outcome. The writing agent
          will ask for anything important that is missing.
        </p>
      </div>
      <div className="post-field">
        <label htmlFor="post-brief">Your work update</label>
        <textarea
          id="post-brief"
          rows={6}
          placeholder="For example: I fixed an out-of-memory crash in the image pipeline by switching to a lower-memory mode, with no measurable speed cost."
          value={brief}
          onChange={e => setBrief(e.target.value)}
          disabled={loading}
        />
        <p className="post-field__hint">Specific details produce a stronger, more credible post.</p>
      </div>
      {mascots.length > 1 && (
        <div className="post-field">
          <label htmlFor="post-mascot">Mascot</label>
          <select id="post-mascot" value={mascot} onChange={e => setChoice(e.target.value)}
            disabled={loading} className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
            {mascots.map(c => (
              <option key={c.character_id} value={c.character_id}>
                {c.display_name || c.character_id}
              </option>
            ))}
          </select>
          <p className="post-field__hint">The character illustrated in this post's image.</p>
        </div>
      )}
      <div className="post-actions">
        <button
          type="submit"
          disabled={loading || !brief.trim()}
          className="post-button post-button--primary"
        >
          {loading ? 'Starting…' : 'Start this post'}
        </button>
      </div>
    </form>
  )
}
