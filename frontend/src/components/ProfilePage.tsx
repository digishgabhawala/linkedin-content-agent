import { useEffect, useState } from 'react'
import { api } from '../api'
import type { ProfileTemplate } from '../types'

export const MAX_PROFILE_CHARS = 8000
const PLACEHOLDER_PATTERN = /\[[^\]\n]+\]/
const START_BLANK = 'start-blank'

interface Props {
  onboarding: boolean
  onSaved: (firstSave: boolean) => void
}

/** The writer profile: who the user is, in Markdown. The draft and the judge
 * read it for every post this user writes. */
export function ProfilePage({ onboarding, onSaved }: Props) {
  const [text, setText] = useState<string | null>(null)
  const [templates, setTemplates] = useState<ProfileTemplate[]>([])
  const [isSet, setIsSet] = useState<boolean | null>(null)
  const [templateChoice, setTemplateChoice] = useState('')
  const [lastTemplateText, setLastTemplateText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let active = true
    api.getProfile()
      .then(profile => {
        if (!active) return
        setText(profile.profile_md ?? '')
        setTemplates(profile.templates)
        setIsSet(profile.is_set)
      })
      .catch((e: unknown) => {
        if (active) setError(e instanceof Error ? e.message : 'Could not load your profile')
      })
    return () => { active = false }
  }, [])

  const length = text?.length ?? 0
  const tooLong = length > MAX_PROFILE_CHARS
  const blank = !text?.trim()
  const hasPlaceholder = PLACEHOLDER_PATTERN.test(text ?? '')

  function chooseTemplate(choice: string) {
    const replacement = choice === START_BLANK
      ? ''
      : templates.find(template => template.id === choice)?.profile_md
    if (replacement === undefined) {
      setTemplateChoice('')
      return
    }
    if (text && text !== lastTemplateText
      && !window.confirm('Replace the profile text you have written?')) return
    setText(replacement)
    setLastTemplateText(replacement)
    setTemplateChoice(choice)
    setNotice(null)
  }

  async function save() {
    if (text === null || tooLong || blank) return
    setSaving(true)
    setError(null)
    setNotice(null)
    try {
      const firstSave = isSet === false
      const saved = await api.saveProfile(text)
      setText(saved.profile_md ?? text)
      setIsSet(saved.is_set)
      setTemplates(saved.templates)
      setNotice('Profile saved.')
      onSaved(firstSave)
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
        <p role="status" className="post-message post-message--warning">
          Before your first post: tell the writer who you are. The draft and the judge use this
          profile. Pick a template or write your own.
        </p>
      )}

      <div className="backdrops-messages" aria-live="polite">
        {error && <p role="alert" className="backdrops-message backdrops-message--error">{error}</p>}
        {notice && <p className="backdrops-message backdrops-message--success">{notice}</p>}
      </div>

      {text === null && !error ? (
        <p role="status" className="backdrops-loading">Loading your profile…</p>
      ) : (
        <div className="post-panel">
          {isSet === false && (
            <div className="post-field">
              <label htmlFor="profile-template">Start from a template</label>
              <select
                id="profile-template"
                className="app-select"
                value={templateChoice}
                onChange={event => chooseTemplate(event.target.value)}
              >
                <option value="">Choose a starting point…</option>
                {templates.map(template => (
                  <option key={template.id} value={template.id}>
                    {template.label} — {template.description}
                  </option>
                ))}
                <option value={START_BLANK}>Start blank</option>
              </select>
              <p className="post-field__hint">Pick a template to start from, or write your own.</p>
            </div>
          )}
          {hasPlaceholder && (
            <p role="status" className="post-message post-message--warning">
              This is a generic profile. Replace the [bracketed] parts with your own details so your posts sound like you.
            </p>
          )}
          <div className="post-field">
            <label htmlFor="writer-profile">Writer profile</label>
            <textarea
              id="writer-profile"
              rows={18}
              value={text ?? ''}
              onChange={e => { setText(e.target.value); setNotice(null) }}
            />
            <p className={tooLong ? 'post-message post-message--danger' : 'post-field__hint'}>
              {length} / {MAX_PROFILE_CHARS}
            </p>
          </div>
          <div className="post-actions">
            <button type="button" onClick={save} disabled={saving || tooLong || blank}
              className="post-button post-button--primary">
              {saving ? 'Saving…' : 'Save profile'}
            </button>
            <button type="button" disabled className="post-button">
              Update profile from template · Coming soon
            </button>
          </div>
        </div>
      )}
    </main>
  )
}
