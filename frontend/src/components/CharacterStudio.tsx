import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { api } from '../api'
import type {
  Character,
  CharacterCardInput,
  HeroCandidate,
  HeroGenerationRun,
  SignatureAttribute,
} from '../types'
import './character-studio.css'

type ViewMode = 'library' | 'create'
type FieldErrors = Record<string, string>

const emptyAttribute = (): SignatureAttribute => ({
  name: '',
  prompt_phrase: '',
  color_hex: null,
})

const emptyCharacter = (): CharacterCardInput => ({
  character_id: '',
  display_name: '',
  style_tag: 'flat vector cartoon mascot',
  species_or_type: 'human',
  base_description: '',
  signature_attributes: [emptyAttribute()],
  personality: '',
  negative_traits: '',
  notes: '',
})

const runIsActive = (run: HeroGenerationRun | null) =>
  run?.status === 'submitting' || run?.status === 'running'

const characterName = (character: Character) =>
  character.display_name || character.character_id.replace(/_/g, ' ')

function readableStatus(status: string) {
  return status.replace(/_/g, ' ')
}

function statusTone(status: string) {
  if (status === 'ready' || status === 'completed') return 'success'
  if (status === 'failed' || status === 'partial_failed') return 'danger'
  if (status === 'promotion_failed') return 'warning'
  return 'info'
}

function formatDate(value: string | null) {
  if (!value) return 'Time unavailable'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function StatusLabel({ status }: { status: string }) {
  return (
    <span className={`studio-status studio-status--${statusTone(status)}`}>
      <span className="studio-status__dot" aria-hidden="true" />
      {readableStatus(status)}
    </span>
  )
}

function CharacterForm({
  onCreated,
  onCancel,
  onDirtyChange,
}: {
  onCreated: (character: Character) => void
  onCancel: () => void
  onDirtyChange: (dirty: boolean) => void
}) {
  const initialForm = useRef(emptyCharacter()).current
  const [form, setForm] = useState<CharacterCardInput>(initialForm)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const summaryRef = useRef<HTMLDivElement>(null)
  const dirty = JSON.stringify(form) !== JSON.stringify(initialForm)

  useEffect(() => {
    if (!dirty || submitting) return
    const warnBeforeLeaving = (event: BeforeUnloadEvent) => {
      event.preventDefault()
    }
    window.addEventListener('beforeunload', warnBeforeLeaving)
    return () => window.removeEventListener('beforeunload', warnBeforeLeaving)
  }, [dirty, submitting])

  useEffect(() => {
    onDirtyChange(dirty)
  }, [dirty, onDirtyChange])

  useEffect(() => () => onDirtyChange(false), [onDirtyChange])

  function cancel() {
    if (!dirty || window.confirm('Discard this unfinished character card?')) onCancel()
  }

  function update<K extends keyof CharacterCardInput>(key: K, value: CharacterCardInput[K]) {
    setForm((current) => ({ ...current, [key]: value }))
    setErrors((current) => {
      if (!current[key]) return current
      const next = { ...current }
      delete next[key]
      return next
    })
  }

  function updateAttribute(index: number, key: keyof SignatureAttribute, value: string) {
    setForm((current) => ({
      ...current,
      signature_attributes: current.signature_attributes.map((attribute, position) =>
        position === index
          ? { ...attribute, [key]: key === 'color_hex' ? value || null : value }
          : attribute,
      ),
    }))
  }

  function validate() {
    const next: FieldErrors = {}
    if (!/^[a-z][a-z0-9_-]{1,63}$/.test(form.character_id)) {
      next.character_id = 'Use 2–64 lowercase letters, numbers, hyphens, or underscores; start with a letter.'
    }
    if (!form.display_name.trim()) next.display_name = 'Add the name people should see.'
    if (!form.base_description.trim()) next.base_description = 'Describe the character’s stable visual identity.'
    if (!form.species_or_type.trim()) next.species_or_type = 'Add a character type.'
    if (!form.style_tag.trim()) next.style_tag = 'Add a visual style.'
    form.signature_attributes.forEach((attribute, index) => {
      const partlyFilled = attribute.name || attribute.prompt_phrase || attribute.color_hex
      if (partlyFilled && (!attribute.name.trim() || !attribute.prompt_phrase.trim())) {
        next[`attribute-${index}`] = 'Add both a name and a prompt phrase, or remove this attribute.'
      }
      if (attribute.color_hex && !/^#[0-9A-Fa-f]{6}$/.test(attribute.color_hex)) {
        next[`attribute-${index}`] = 'Use a six-digit hex colour such as #4946C7.'
      }
    })
    return next
  }

  function focusField(field: string) {
    const target = document.getElementById(field)
    if (!target) return
    if (target.matches('input, textarea, select, button')) target.focus()
    else target.querySelector<HTMLElement>('input, textarea, select, button')?.focus()
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    const nextErrors = validate()
    setErrors(nextErrors)
    setSubmitError(null)
    if (Object.keys(nextErrors).length > 0) {
      window.requestAnimationFrame(() => summaryRef.current?.focus())
      return
    }

    setSubmitting(true)
    try {
      const payload = {
        ...form,
        character_id: form.character_id.trim(),
        display_name: form.display_name.trim(),
        base_description: form.base_description.trim(),
        style_tag: form.style_tag.trim(),
        species_or_type: form.species_or_type.trim(),
        personality: form.personality.trim(),
        negative_traits: form.negative_traits.trim(),
        notes: form.notes.trim(),
        signature_attributes: form.signature_attributes.filter(
          (attribute) => attribute.name.trim() && attribute.prompt_phrase.trim(),
        ),
      }
      onCreated(await api.createCharacter(payload))
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : 'Could not create this character.')
      window.requestAnimationFrame(() => summaryRef.current?.focus())
    } finally {
      setSubmitting(false)
    }
  }

  const errorEntries = Object.entries(errors)

  return (
    <section className="studio-create" aria-labelledby="new-character-title">
      <div className="studio-section-heading">
        <div>
          <p className="studio-eyebrow">Character card</p>
          <h2 id="new-character-title">Define a reusable visual identity</h2>
          <p>
            These details travel with every hero candidate, making later post images consistent and reproducible.
          </p>
        </div>
        <button className="studio-button studio-button--quiet" type="button" onClick={cancel}>
          Back to library
        </button>
      </div>

      <form onSubmit={submit} noValidate autoComplete="off" className="studio-form">
        {(errorEntries.length > 0 || submitError) && (
          <div className="studio-error-summary" role="alert" tabIndex={-1} ref={summaryRef}>
            <h3>Check the character card</h3>
            {submitError && <p>{submitError}</p>}
            {errorEntries.length > 0 && (
              <ul>
                {errorEntries.map(([field, message]) => (
                  <li key={field}>
                    <button type="button" className="studio-error-link" onClick={() => focusField(field)}>
                      {message}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <fieldset className="studio-fieldset">
          <legend>Identity</legend>
          <p className="studio-fieldset__intro">The stable name and reference used by other AI Bharatiyaa tools.</p>
          <div className="studio-form-grid">
            <label className="studio-field" htmlFor="character_id">
              <span>Character ID <span aria-hidden="true">*</span></span>
              <input
                id="character_id"
                name="character_id"
                value={form.character_id}
                onChange={(event) => update('character_id', event.target.value.toLowerCase())}
                aria-invalid={Boolean(errors.character_id)}
                aria-describedby={`character-id-help${errors.character_id ? ' character-id-error' : ''}`}
                autoComplete="off"
                spellCheck={false}
                required
                placeholder="e.g. pragmatic_dev…"
              />
              <small id="character-id-help">A permanent, URL-safe ID. It cannot be changed later.</small>
              {errors.character_id && <small id="character-id-error" className="studio-field__error">{errors.character_id}</small>}
            </label>
            <label className="studio-field" htmlFor="display_name">
              <span>Display name <span aria-hidden="true">*</span></span>
              <input
                id="display_name"
                name="display_name"
                value={form.display_name}
                onChange={(event) => update('display_name', event.target.value)}
                aria-invalid={Boolean(errors.display_name)}
                aria-describedby={errors.display_name ? 'display-name-error' : undefined}
                autoComplete="off"
                required
                placeholder="e.g. Pragmatic Developer…"
              />
              {errors.display_name && <small id="display-name-error" className="studio-field__error">{errors.display_name}</small>}
            </label>
          </div>
        </fieldset>

        <fieldset className="studio-fieldset">
          <legend>Visual foundation</legend>
          <p className="studio-fieldset__intro">Describe only traits that should remain true across every scene.</p>
          <label className="studio-field" htmlFor="base_description">
            <span>Base description <span aria-hidden="true">*</span></span>
            <textarea
              id="base_description"
              name="base_description"
              rows={4}
              value={form.base_description}
              onChange={(event) => update('base_description', event.target.value)}
              aria-invalid={Boolean(errors.base_description)}
              aria-describedby={`base-description-help${errors.base_description ? ' base-description-error' : ''}`}
              autoComplete="off"
              required
              placeholder="e.g. An Indian software developer in their early thirties, warm expression, clean silhouette…"
            />
            <small id="base-description-help">Include age range, build, face, hair, and other traits that identify the character.</small>
            {errors.base_description && <small id="base-description-error" className="studio-field__error">{errors.base_description}</small>}
          </label>
          <div className="studio-form-grid">
            <label className="studio-field" htmlFor="species_or_type">
              <span>Character type <span aria-hidden="true">*</span></span>
              <input
                id="species_or_type"
                name="species_or_type"
                value={form.species_or_type}
                onChange={(event) => update('species_or_type', event.target.value)}
                aria-invalid={Boolean(errors.species_or_type)}
                aria-describedby={errors.species_or_type ? 'species-type-error' : undefined}
                autoComplete="off"
                required
              />
              {errors.species_or_type && <small id="species-type-error" className="studio-field__error">{errors.species_or_type}</small>}
            </label>
            <label className="studio-field" htmlFor="style_tag">
              <span>Visual style <span aria-hidden="true">*</span></span>
              <input
                id="style_tag"
                name="style_tag"
                value={form.style_tag}
                onChange={(event) => update('style_tag', event.target.value)}
                aria-invalid={Boolean(errors.style_tag)}
                aria-describedby={errors.style_tag ? 'style-tag-error' : undefined}
                autoComplete="off"
                required
              />
              {errors.style_tag && <small id="style-tag-error" className="studio-field__error">{errors.style_tag}</small>}
            </label>
          </div>
        </fieldset>

        <fieldset className="studio-fieldset">
          <legend>Signature attributes</legend>
          <p className="studio-fieldset__intro">Add up to three visual anchors that should recur in every render.</p>
          <div className="studio-attribute-list">
            {form.signature_attributes.map((attribute, index) => (
              <div className="studio-attribute" key={index} id={`attribute-${index}`}>
                <div className="studio-attribute__number" aria-hidden="true">{String(index + 1).padStart(2, '0')}</div>
                <label className="studio-field">
                  <span>Attribute name</span>
                  <input
                    name={`signature_attribute_${index}_name`}
                    value={attribute.name}
                    onChange={(event) => updateAttribute(index, 'name', event.target.value)}
                    aria-invalid={Boolean(errors[`attribute-${index}`])}
                    aria-describedby={errors[`attribute-${index}`] ? `attribute-${index}-error` : undefined}
                    autoComplete="off"
                    placeholder="e.g. Indigo hoodie…"
                  />
                </label>
                <label className="studio-field studio-attribute__prompt">
                  <span>Prompt phrase</span>
                  <input
                    name={`signature_attribute_${index}_prompt`}
                    value={attribute.prompt_phrase}
                    onChange={(event) => updateAttribute(index, 'prompt_phrase', event.target.value)}
                    aria-invalid={Boolean(errors[`attribute-${index}`])}
                    aria-describedby={errors[`attribute-${index}`] ? `attribute-${index}-error` : undefined}
                    autoComplete="off"
                    placeholder="e.g. Wearing a plain indigo zip hoodie…"
                  />
                </label>
                <label className="studio-field studio-field--colour">
                  <span>Colour</span>
                  <input
                    name={`signature_attribute_${index}_colour`}
                    value={attribute.color_hex ?? ''}
                    onChange={(event) => updateAttribute(index, 'color_hex', event.target.value)}
                    aria-invalid={Boolean(errors[`attribute-${index}`])}
                    aria-describedby={errors[`attribute-${index}`] ? `attribute-${index}-error` : undefined}
                    autoComplete="off"
                    spellCheck={false}
                    placeholder="e.g. #4946C7…"
                  />
                </label>
                {form.signature_attributes.length > 1 && (
                  <button
                    className="studio-text-action studio-attribute__remove"
                    type="button"
                    onClick={() => update('signature_attributes', form.signature_attributes.filter((_, position) => position !== index))}
                  >
                    Remove
                  </button>
                )}
                {errors[`attribute-${index}`] && (
                  <p id={`attribute-${index}-error`} className="studio-field__error studio-attribute__error">{errors[`attribute-${index}`]}</p>
                )}
              </div>
            ))}
          </div>
          {form.signature_attributes.length < 3 && (
            <button
              className="studio-button studio-button--secondary"
              type="button"
              onClick={() => update('signature_attributes', [...form.signature_attributes, emptyAttribute()])}
            >
              Add signature attribute
            </button>
          )}
        </fieldset>

        <fieldset className="studio-fieldset">
          <legend>Voice and guardrails</legend>
          <p className="studio-fieldset__intro">Optional context helps the image model preserve the intended character.</p>
          <div className="studio-form-grid">
            <label className="studio-field" htmlFor="personality">
              <span>Personality</span>
              <textarea
                id="personality"
                name="personality"
                rows={3}
                value={form.personality}
                onChange={(event) => update('personality', event.target.value)}
                autoComplete="off"
                placeholder="e.g. Practical, curious, quietly confident…"
              />
            </label>
            <label className="studio-field" htmlFor="negative_traits">
              <span>Avoid</span>
              <textarea
                id="negative_traits"
                name="negative_traits"
                rows={3}
                value={form.negative_traits}
                onChange={(event) => update('negative_traits', event.target.value)}
                autoComplete="off"
                placeholder="e.g. Corporate stock-photo look, exaggerated muscles…"
              />
            </label>
          </div>
          <label className="studio-field" htmlFor="notes">
            <span>Internal notes</span>
            <textarea
              id="notes"
              name="notes"
              rows={3}
              value={form.notes}
              onChange={(event) => update('notes', event.target.value)}
              autoComplete="off"
              placeholder="e.g. Context for future collaborators; not a substitute for visual traits…"
            />
          </label>
        </fieldset>

        <div className="studio-form-actions">
          <button className="studio-button studio-button--primary" type="submit" disabled={submitting}>
            {submitting ? 'Creating character…' : 'Create character'}
          </button>
          <button className="studio-button studio-button--quiet" type="button" onClick={cancel} disabled={submitting}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  )
}

function CandidateCard({
  candidate,
  characterName: name,
  locking,
  onLock,
}: {
  candidate: HeroCandidate
  characterName: string
  locking: boolean
  onLock: () => void
}) {
  const canLock = candidate.status === 'ready' && !candidate.is_active_hero
  return (
    <article className={`studio-candidate${candidate.is_active_hero ? ' studio-candidate--active' : ''}`}>
      <div className="studio-candidate__image">
        {candidate.image_url ? (
          <img
            src={candidate.image_url}
            alt={`${name} hero candidate, seed ${candidate.seed}`}
            loading="lazy"
            width="640"
            height="640"
          />
        ) : (
          <div className="studio-candidate__placeholder" aria-hidden="true">
            <span className="studio-candidate__seed">{candidate.seed}</span>
            <span>{candidate.status === 'failed' ? 'No image' : 'Rendering'}</span>
          </div>
        )}
        <div className="studio-candidate__status"><StatusLabel status={candidate.status} /></div>
      </div>
      <div className="studio-candidate__body">
        <div>
          <p className="studio-mono">Seed {candidate.seed}</p>
          <p className="studio-candidate__id" title={candidate.id}>Candidate {candidate.id.slice(0, 8)}</p>
        </div>
        {candidate.is_active_hero ? (
          <span className="studio-current-hero">Current hero</span>
        ) : (
          <button
            className="studio-button studio-button--secondary"
            type="button"
            onClick={onLock}
            disabled={!canLock || locking}
          >
            {locking ? 'Locking…' : 'Use as hero'}
          </button>
        )}
      </div>
      {candidate.error && <p className="studio-candidate__error">{candidate.error}</p>}
    </article>
  )
}

function CharacterWorkspace({
  character,
  runs,
  selectedRun,
  onSelectRun,
  onRunCreated,
  onRunUpdated,
  onHeroLocked,
}: {
  character: Character
  runs: HeroGenerationRun[]
  selectedRun: HeroGenerationRun | null
  onSelectRun: (id: string) => void
  onRunCreated: (run: HeroGenerationRun) => void
  onRunUpdated: (run: HeroGenerationRun) => void
  onHeroLocked: (character: Character, candidateId: string) => void
}) {
  const [candidateCount, setCandidateCount] = useState(4)
  const [profile, setProfile] = useState<'full' | 'lightning'>('full')
  const [baseSeed, setBaseSeed] = useState('')
  const [generating, setGenerating] = useState(false)
  const [lockingId, setLockingId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const pollRunId = selectedRun?.id
  const pollRunStatus = selectedRun?.status

  useEffect(() => {
    if (!pollRunId || (pollRunStatus !== 'submitting' && pollRunStatus !== 'running')) return
    let active = true
    let inFlight = false
    const poll = async () => {
      if (inFlight) return
      inFlight = true
      try {
        const updated = await api.getHeroGeneration(character.character_id, pollRunId)
        if (active) onRunUpdated(updated)
      } catch (error) {
        if (active) setActionError(error instanceof Error ? error.message : 'Could not refresh candidate progress.')
      } finally {
        inFlight = false
      }
    }
    void poll()
    const interval = window.setInterval(poll, 5000)
    return () => {
      active = false
      window.clearInterval(interval)
    }
  }, [character.character_id, onRunUpdated, pollRunId, pollRunStatus])

  async function generate(event: FormEvent) {
    event.preventDefault()
    setActionError(null)
    setSuccessMessage(null)
    const parsedSeed = baseSeed.trim() ? Number(baseSeed) : undefined
    if (parsedSeed !== undefined && (!Number.isInteger(parsedSeed) || parsedSeed < 0)) {
      setActionError('Base seed must be a non-negative whole number.')
      return
    }
    setGenerating(true)
    try {
      const run = await api.startHeroGeneration(character.character_id, {
        candidate_count: candidateCount,
        profile,
        ...(parsedSeed === undefined ? {} : { base_seed: parsedSeed }),
      })
      onRunCreated(run)
      setSuccessMessage(`${candidateCount} candidates submitted to the render queue.`)
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Could not start candidate generation.')
    } finally {
      setGenerating(false)
    }
  }

  async function lock(candidate: HeroCandidate) {
    setLockingId(candidate.id)
    setActionError(null)
    setSuccessMessage(null)
    try {
      const result = await api.lockHeroCandidate(character.character_id, candidate.id)
      onHeroLocked(result.character, result.candidate.id)
      setSuccessMessage(`Seed ${candidate.seed} is now ${characterName(result.character)}’s hero image.`)
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Could not lock this candidate.')
    } finally {
      setLockingId(null)
    }
  }

  const readyCount = selectedRun?.candidates.filter((candidate) => candidate.status === 'ready').length ?? 0
  const failedCount = selectedRun?.candidates.filter((candidate) => candidate.status === 'failed').length ?? 0

  return (
    <div className="studio-workspace">
      <section className="studio-character-header" aria-labelledby="selected-character-title">
        <div className="studio-character-header__copy">
          <p className="studio-eyebrow">Character reference</p>
          <h2 id="selected-character-title">{characterName(character)}</h2>
          <p>{character.character_card.base_description}</p>
          <div className="studio-character-meta">
            <span className="studio-mono" translate="no">{character.character_id}</span>
            <span>Hero v{character.hero_version}</span>
            <span>{character.character_card.style_tag}</span>
          </div>
        </div>
        <div className="studio-hero-reference">
          {character.hero_image_url ? (
            <img src={character.hero_image_url} alt={`${characterName(character)} current hero reference`} width="220" height="220" fetchPriority="high" />
          ) : (
            <div className="studio-hero-reference__empty">
              <span aria-hidden="true">01</span>
              <strong>No hero locked</strong>
              <small>Generate candidates below</small>
            </div>
          )}
        </div>
      </section>

      <section className="studio-generation" aria-labelledby="generation-title">
        <div className="studio-section-heading studio-section-heading--compact">
          <div>
            <p className="studio-eyebrow">Render brief</p>
            <h2 id="generation-title">Create hero candidates</h2>
            <p>Each candidate becomes an independent task. You can review completed images while others are still rendering.</p>
          </div>
        </div>
        <form className="studio-generation-form" onSubmit={generate}>
          <label className="studio-field" htmlFor="candidate-count">
            <span>Candidate count</span>
            <select
              id="candidate-count"
              name="candidate_count"
              value={candidateCount}
              onChange={(event) => setCandidateCount(Number(event.target.value))}
              disabled={generating}
            >
              {[1, 2, 4, 6, 8, 12].map((count) => <option key={count} value={count}>{count}</option>)}
            </select>
          </label>
          <fieldset className="studio-profile-options">
            <legend>Render profile</legend>
            <label>
              <input type="radio" name="profile" value="full" checked={profile === 'full'} onChange={() => setProfile('full')} />
              <span><strong>Full</strong><small>Highest quality, slower</small></span>
            </label>
            <label>
              <input type="radio" name="profile" value="lightning" checked={profile === 'lightning'} onChange={() => setProfile('lightning')} />
              <span><strong>Lightning</strong><small>Faster exploration</small></span>
            </label>
          </fieldset>
          <details className="studio-advanced">
            <summary>Advanced</summary>
            <label className="studio-field" htmlFor="base-seed">
              <span>Base seed</span>
              <input
                id="base-seed"
                name="base_seed"
                type="number"
                min="0"
                step="1"
                inputMode="numeric"
                value={baseSeed}
                onChange={(event) => setBaseSeed(event.target.value)}
                autoComplete="off"
                placeholder="Generated automatically…"
              />
              <small>Candidate seeds increment from this number.</small>
            </label>
          </details>
          <button className="studio-button studio-button--primary studio-generation-form__submit" type="submit" disabled={generating}>
            {generating ? 'Submitting tasks…' : 'Generate candidates'}
          </button>
        </form>
        <div className="studio-live-region" aria-live="polite" aria-atomic="true">
          {successMessage && <p className="studio-notice studio-notice--success">{successMessage}</p>}
          {actionError && <p className="studio-notice studio-notice--danger">{actionError} Try again when the service is available.</p>}
        </div>
      </section>

      <section className="studio-contact-sheet" aria-labelledby="candidate-review-title">
        <div className="studio-section-heading studio-section-heading--compact">
          <div>
            <p className="studio-eyebrow">Contact sheet</p>
            <h2 id="candidate-review-title">Review and lock</h2>
          </div>
          {selectedRun && (
            <div className="studio-run-summary" role="status">
              <StatusLabel status={selectedRun.status} />
              <span>{readyCount}/{selectedRun.requested_candidates} ready</span>
              {failedCount > 0 && <span>{failedCount} failed</span>}
            </div>
          )}
        </div>

        {runs.length > 0 && (
          <div className="studio-run-strip" aria-label="Generation history">
            {runs.map((run, index) => (
              <button
                type="button"
                key={run.id}
                className={run.id === selectedRun?.id ? 'is-selected' : ''}
                aria-pressed={run.id === selectedRun?.id}
                onClick={() => onSelectRun(run.id)}
              >
                <span>Run {runs.length - index}</span>
                <small>{formatDate(run.created_at)}</small>
              </button>
            ))}
          </div>
        )}

        {!selectedRun ? (
          <div className="studio-empty-state">
            <span className="studio-empty-state__index" aria-hidden="true">00</span>
            <h3>No candidates yet</h3>
            <p>Choose a render profile above and submit the first set. Results will appear here as each task completes.</p>
          </div>
        ) : (
          <>
            {runIsActive(selectedRun) && (
              <p className="studio-progress-note" role="status">
                The queue is working. This page checks for completed candidates every five seconds; you can safely continue other work.
              </p>
            )}
            <div className="studio-candidate-grid">
              {selectedRun.candidates.map((candidate) => (
                <CandidateCard
                  key={candidate.id}
                  candidate={candidate}
                  characterName={characterName(character)}
                  locking={lockingId === candidate.id}
                  onLock={() => lock(candidate)}
                />
              ))}
            </div>
          </>
        )}
      </section>
    </div>
  )
}

export function CharacterStudio({ onDirtyChange }: { onDirtyChange: (dirty: boolean) => void }) {
  const [characters, setCharacters] = useState<Character[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [runs, setRuns] = useState<HeroGenerationRun[]>([])
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [mode, setMode] = useState<ViewMode>('library')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const selectedCharacter = useMemo(
    () => characters.find((character) => character.character_id === selectedId) ?? null,
    [characters, selectedId],
  )
  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? null,
    [runs, selectedRunId],
  )

  useEffect(() => {
    let active = true
    setLoading(true)
    api.listCharacters()
      .then((items) => {
        if (!active) return
        setCharacters(items)
        setSelectedId((current) => current ?? items[0]?.character_id ?? null)
        setLoadError(null)
      })
      .catch((error) => {
        if (active) setLoadError(error instanceof Error ? error.message : 'Could not load the character library.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!selectedId) {
      setRuns([])
      setSelectedRunId(null)
      return
    }
    let active = true
    api.listHeroGenerations(selectedId)
      .then((items) => {
        if (!active) return
        setRuns(items)
        setSelectedRunId(items[0]?.id ?? null)
        setLoadError(null)
      })
      .catch((error) => {
        if (active) setLoadError(error instanceof Error ? error.message : 'Could not load generation history.')
      })
    return () => { active = false }
  }, [selectedId])

  const created = useCallback((character: Character) => {
    setCharacters((current) => [...current, character].sort((a, b) => a.character_id.localeCompare(b.character_id)))
    setSelectedId(character.character_id)
    setMode('library')
  }, [])

  const heroLocked = useCallback((character: Character, candidateId: string) => {
    setCharacters((current) => current.map((item) => item.character_id === character.character_id ? character : item))
    setRuns((current) => current.map((run) => ({
      ...run,
      candidates: run.candidates.map((candidate) => ({
        ...candidate,
        is_active_hero: candidate.id === candidateId,
      })),
    })))
  }, [])

  const addRun = useCallback((run: HeroGenerationRun) => {
    setRuns((current) => [run, ...current])
    setSelectedRunId(run.id)
  }, [])

  const updateRun = useCallback((run: HeroGenerationRun) => {
    setRuns((current) => current.map((item) => item.id === run.id ? run : item))
  }, [])

  return (
    <main id="characters-main-content" className="studio-page">
      <header className="studio-page-heading">
        <div>
          <p className="studio-eyebrow">Identity system</p>
          <h1>Character Studio</h1>
          <p>Build a durable visual reference once, then reuse it across every LinkedIn scene.</p>
        </div>
        {mode === 'library' && (
          <button className="studio-button studio-button--primary" type="button" onClick={() => setMode('create')}>
            New character
          </button>
        )}
      </header>

      {loadError && <p className="studio-notice studio-notice--danger" role="alert">{loadError} Refresh the page to try again.</p>}

      {mode === 'create' ? (
        <CharacterForm
          onCreated={created}
          onCancel={() => setMode('library')}
          onDirtyChange={onDirtyChange}
        />
      ) : (
        <div className="studio-layout">
          <aside className="studio-library" aria-labelledby="character-library-title">
            <div className="studio-library__heading">
              <h2 id="character-library-title">Library</h2>
              <span>{characters.length}</span>
            </div>
            {loading ? (
              <div className="studio-library__loading" role="status">Loading characters…</div>
            ) : characters.length === 0 ? (
              <div className="studio-library__empty">
                <p>No characters yet.</p>
                <button className="studio-text-action" type="button" onClick={() => setMode('create')}>Create the first one</button>
              </div>
            ) : (
              <div className="studio-library__list">
                {characters.map((character) => (
                  <button
                    key={character.character_id}
                    type="button"
                    className={character.character_id === selectedId ? 'is-selected' : ''}
                    aria-pressed={character.character_id === selectedId}
                    onClick={() => setSelectedId(character.character_id)}
                  >
                    <span className="studio-library__thumb">
                      {character.hero_image_url
                        ? <img src={character.hero_image_url} alt="" width="48" height="48" />
                        : <span aria-hidden="true">{characterName(character).slice(0, 1).toUpperCase()}</span>}
                    </span>
                    <span className="studio-library__copy">
                      <strong>{characterName(character)}</strong>
                      <small className="studio-mono" translate="no">{character.character_id}</small>
                    </span>
                    <span className={`studio-library__hero-state${character.hero_image_url ? ' is-ready' : ''}`}>
                      {character.hero_image_url ? `v${character.hero_version}` : 'No hero'}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </aside>

          {selectedCharacter ? (
            <CharacterWorkspace
              key={selectedCharacter.character_id}
              character={selectedCharacter}
              runs={runs}
              selectedRun={selectedRun}
              onSelectRun={setSelectedRunId}
              onRunCreated={addRun}
              onRunUpdated={updateRun}
              onHeroLocked={heroLocked}
            />
          ) : !loading && characters.length === 0 ? (
            <section className="studio-welcome" aria-labelledby="empty-studio-title">
              <span className="studio-welcome__mark" aria-hidden="true">ai</span>
              <p className="studio-eyebrow">Start with identity</p>
              <h2 id="empty-studio-title">Create your first recurring character</h2>
              <p>A character card keeps visual identity separate from each post’s one-time scene. That is the foundation for repeatable image generation.</p>
              <button className="studio-button studio-button--primary" type="button" onClick={() => setMode('create')}>Create character</button>
            </section>
          ) : null}
        </div>
      )}
    </main>
  )
}
