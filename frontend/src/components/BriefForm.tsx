import { useState, type FormEvent } from 'react'

interface Props {
  onSubmit: (brief: string) => void
  loading: boolean
}

export function BriefForm({ onSubmit, loading }: Props) {
  const [brief, setBrief] = useState('')

  function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    if (!brief.trim() || loading) return
    onSubmit(brief.trim())
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
