import { useEffect, useState } from 'react'
import { api } from '../api'

export const MAX_PROFILE_CHARS = 8000

interface Props {
  onboarding: boolean
  onSaved: () => void
}

/** The writer profile: who the user is, in Markdown. The draft and the judge
 * read it for every post this user writes. */
export function ProfilePage({ onboarding, onSaved }: Props) {
  const [text, setText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let active = true
    api.getProfile()
      .then(profile => { if (active) setText(profile.profile_md ?? profile.template) })
      .catch((e: unknown) => {
        if (active) setError(e instanceof Error ? e.message : 'Could not load your profile')
      })
    return () => { active = false }
  }, [])

  const length = text?.length ?? 0
  const tooLong = length > MAX_PROFILE_CHARS
  const blank = !text?.trim()

  async function save() {
    if (text === null || tooLong || blank) return
    setSaving(true)
    setError(null)
    setNotice(null)
    try {
      const saved = await api.saveProfile(text)
      setText(saved.profile_md ?? text)
      setNotice('Profile saved.')
      onSaved()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Could not save your profile')
    } finally {
      setSaving(false)
    }
  }

  return (
    <main id="profile-main-content" className="backdrops-page">
      <section className="backdrops-hero" aria-labelledby="profile-heading">
        <div>
          <p className="backdrops-eyebrow">About the writer</p>
          <h2 id="profile-heading">Profile</h2>
          <p>Who you are, what you work on and how you sound. Markdown, up to 8,000 characters.</p>
        </div>
      </section>

      {onboarding && (
        <p role="status" className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          Before your first post: tell the writer who you are. The draft and the judge use this
          profile. Start from the template below and make it yours.
        </p>
      )}

      <div className="backdrops-messages" aria-live="polite">
        {error && <p role="alert" className="backdrops-message backdrops-message--error">{error}</p>}
        {notice && <p className="backdrops-message backdrops-message--success">{notice}</p>}
      </div>

      {text === null && !error ? (
        <p role="status" className="backdrops-loading">Loading your profile…</p>
      ) : (
        <div className="post-panel space-y-3">
          <div className="post-field">
            <label htmlFor="writer-profile">Writer profile</label>
            <textarea
              id="writer-profile"
              rows={18}
              value={text ?? ''}
              onChange={e => { setText(e.target.value); setNotice(null) }}
              className="font-mono text-sm"
            />
            <p className={`post-field__hint ${tooLong ? 'text-red-700' : ''}`}>
              {length} / {MAX_PROFILE_CHARS}
            </p>
          </div>
          <div className="post-actions">
            <button type="button" onClick={save} disabled={saving || tooLong || blank}
              className="post-button post-button--primary">
              {saving ? 'Saving…' : 'Save profile'}
            </button>
          </div>
        </div>
      )}
    </main>
  )
}
