import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../api'
import type { SceneAsset, SceneAssetVersion } from '../types'

function identifierFor(label: string) {
  return label.trim().toLowerCase().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '')
}

function formatDate(value: string | null) {
  if (!value) return 'Date unavailable'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function errorMessage(cause: unknown, fallback: string) {
  return cause instanceof Error && cause.message ? cause.message : fallback
}

export function BackdropsPage() {
  const [assets, setAssets] = useState<SceneAsset[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDetail, setNewDetail] = useState('')
  const [editingName, setEditingName] = useState<string | null>(null)
  const [editLabel, setEditLabel] = useState('')
  const [editDetail, setEditDetail] = useState('')
  const [historyName, setHistoryName] = useState<string | null>(null)
  const [versions, setVersions] = useState<SceneAssetVersion[]>([])
  const [pending, setPending] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function refresh() {
    try {
      setAssets(await api.listSceneAssets(true))
      setError(null)
    } catch (cause) {
      setError(errorMessage(cause, 'Could not load backdrops'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  async function refreshHistory(name: string) {
    const next = await api.listSceneAssetVersions(name)
    setVersions(next)
    setHistoryName(name)
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault()
    setPending('create')
    setNotice(null)
    try {
      const created = await api.createSceneAsset(newName, newDetail)
      setNewName('')
      setNewDetail('')
      setCreateOpen(false)
      setNotice(`${created.display_name} is ready to use in posts.`)
      await refresh()
    } catch (cause) {
      setError(errorMessage(cause, 'Could not create backdrop'))
    } finally {
      setPending(null)
    }
  }

  async function handleSave(asset: SceneAsset) {
    setPending(`save:${asset.name}`)
    setNotice(null)
    try {
      const updated = await api.updateSceneAsset(asset.name, editLabel, editDetail)
      setEditingName(null)
      setNotice(
        updated.current_version === asset.current_version
          ? `${updated.display_name} was updated.`
          : `${updated.display_name} version ${updated.current_version} was created.`,
      )
      await refresh()
      if (historyName === asset.name) await refreshHistory(asset.name)
    } catch (cause) {
      setError(errorMessage(cause, `Could not update ${asset.display_name}`))
    } finally {
      setPending(null)
    }
  }

  async function handleArchive(asset: SceneAsset) {
    if (!window.confirm(
      `Archive “${asset.display_name}”? Existing posts keep their pinned versions, but new posts will no longer reuse it.`,
    )) return
    setPending(`archive:${asset.name}`)
    setNotice(null)
    try {
      await api.archiveSceneAsset(asset.name)
      setNotice(`${asset.display_name} was archived.`)
      if (historyName === asset.name) {
        setHistoryName(null)
        setVersions([])
      }
      await refresh()
    } catch (cause) {
      setError(errorMessage(cause, `Could not archive ${asset.display_name}`))
    } finally {
      setPending(null)
    }
  }

  async function handleUnarchive(asset: SceneAsset) {
    setPending(`unarchive:${asset.name}`)
    setNotice(null)
    try {
      await api.unarchiveSceneAsset(asset.name)
      setNotice(`${asset.display_name} is active again.`)
      await refresh()
    } catch (cause) {
      setError(errorMessage(cause, `Could not restore ${asset.display_name}`))
    } finally {
      setPending(null)
    }
  }

  async function toggleHistory(asset: SceneAsset) {
    if (historyName === asset.name) {
      setHistoryName(null)
      setVersions([])
      return
    }
    setPending(`history:${asset.name}`)
    try {
      await refreshHistory(asset.name)
      setError(null)
    } catch (cause) {
      setError(errorMessage(cause, `Could not load ${asset.display_name} history`))
    } finally {
      setPending(null)
    }
  }

  async function handleRestoreVersion(asset: SceneAsset, version: number) {
    setPending(`restore:${asset.name}:${version}`)
    setNotice(null)
    try {
      const restored = await api.restoreSceneAssetVersion(asset.name, version)
      setNotice(
        `Version ${version} was restored as new version ${restored.current_version} of ${restored.display_name}.`,
      )
      await refresh()
      await refreshHistory(asset.name)
    } catch (cause) {
      setError(errorMessage(cause, `Could not restore version ${version}`))
    } finally {
      setPending(null)
    }
  }

  const active = assets.filter(asset => !asset.archived_at)
  const archived = assets.filter(asset => asset.archived_at)
  const identifier = identifierFor(newName)

  function renderCard(asset: SceneAsset) {
    const isEditing = editingName === asset.name
    const isArchived = Boolean(asset.archived_at)
    return (
      <article key={asset.name} className="backdrop-card">
        <div className="backdrop-card__topline">
          <div className="backdrop-card__identity">
            <h4>{asset.display_name}</h4>
            <code>@{asset.name}</code>
          </div>
          <span className={isArchived ? 'backdrop-status backdrop-status--archived' : 'backdrop-status'}>
            {isArchived ? 'Archived' : `Version ${asset.current_version}`}
          </span>
        </div>

        <div className="backdrop-card__meta" aria-label="Backdrop usage and update details">
          <span>{asset.usage_count} {asset.usage_count === 1 ? 'post' : 'posts'}</span>
          <span>Updated {formatDate(asset.updated_at)}</span>
        </div>

        {isEditing ? (
          <div className="backdrop-editor">
            <label htmlFor={`backdrop-${asset.name}-label`}>Display name</label>
            <input
              id={`backdrop-${asset.name}-label`}
              value={editLabel}
              onChange={event => setEditLabel(event.target.value)}
            />
            <p className="backdrop-field-note">Stable ID stays <code>@{asset.name}</code>.</p>
            <label htmlFor={`backdrop-${asset.name}-detail`}>Description</label>
            <textarea
              id={`backdrop-${asset.name}-detail`}
              rows={4}
              value={editDetail}
              onChange={event => setEditDetail(event.target.value)}
            />
            <p className="backdrop-field-note">Changing the description creates a new immutable version.</p>
            <div className="backdrop-actions">
              <button
                type="button"
                className="backdrop-button backdrop-button--primary"
                disabled={!editLabel.trim() || !editDetail.trim() || pending === `save:${asset.name}`}
                onClick={() => handleSave(asset)}
              >
                {pending === `save:${asset.name}` ? 'Saving…' : 'Save changes'}
              </button>
              <button type="button" className="backdrop-button" onClick={() => setEditingName(null)}>
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <>
            <p className="backdrop-card__description">{asset.detail_text}</p>
            <div className="backdrop-actions">
              {!isArchived && (
                <button
                  type="button"
                  className="backdrop-button"
                  onClick={() => {
                    setEditingName(asset.name)
                    setEditLabel(asset.display_name)
                    setEditDetail(asset.detail_text)
                  }}
                >
                  Edit
                </button>
              )}
              <button
                type="button"
                className="backdrop-button"
                aria-expanded={historyName === asset.name}
                onClick={() => toggleHistory(asset)}
                disabled={pending === `history:${asset.name}`}
              >
                {pending === `history:${asset.name}`
                  ? 'Loading…'
                  : historyName === asset.name ? 'Hide history' : 'Version history'}
              </button>
              {isArchived ? (
                <button
                  type="button"
                  className="backdrop-button backdrop-button--primary"
                  onClick={() => handleUnarchive(asset)}
                  disabled={pending === `unarchive:${asset.name}`}
                >
                  {pending === `unarchive:${asset.name}` ? 'Restoring…' : 'Restore backdrop'}
                </button>
              ) : (
                <button
                  type="button"
                  className="backdrop-button backdrop-button--quiet-danger"
                  onClick={() => handleArchive(asset)}
                  disabled={pending === `archive:${asset.name}`}
                >
                  {pending === `archive:${asset.name}` ? 'Archiving…' : 'Archive'}
                </button>
              )}
            </div>
          </>
        )}

        {historyName === asset.name && (
          <ol className="backdrop-history" aria-label={`${asset.display_name} version history`}>
            {versions.map(version => (
              <li key={version.id} className="backdrop-history__item">
                <div className="backdrop-history__heading">
                  <div>
                    <strong>Version {version.version}</strong>
                    <span>{formatDate(version.created_at)}</span>
                  </div>
                  {version.version !== asset.current_version && (
                    <button
                      type="button"
                      className="backdrop-button"
                      disabled={pending === `restore:${asset.name}:${version.version}`}
                      onClick={() => handleRestoreVersion(asset, version.version)}
                    >
                      {pending === `restore:${asset.name}:${version.version}`
                        ? 'Restoring…' : 'Restore as new version'}
                    </button>
                  )}
                </div>
                <p>{version.detail_text}</p>
                <details className="backdrop-usage">
                  <summary>
                    Used by {version.usage_count} {version.usage_count === 1 ? 'post' : 'posts'}
                  </summary>
                  {version.posts.length > 0 ? (
                    <ul>
                      {version.posts.map(post => (
                        <li key={post.id}>
                          <a href={`#posts?post=${post.id}`}>{post.brief}</a>
                          <span>{post.status.replace(/_/g, ' ')}</span>
                        </li>
                      ))}
                    </ul>
                  ) : <p>No posts are pinned to this version.</p>}
                </details>
              </li>
            ))}
          </ol>
        )}
      </article>
    )
  }

  return (
    <main id="backdrops-main-content" className="backdrops-page">
      <section className="backdrops-hero" aria-labelledby="backdrops-heading">
        <div>
          <p className="backdrops-eyebrow">Visual consistency library</p>
          <h2 id="backdrops-heading">Backdrops</h2>
          <p>
            Keep recurring places consistent across posts. Every description edit creates a version,
            so published work keeps the exact backdrop it used.
          </p>
        </div>
        <button
          type="button"
          className="backdrop-button backdrop-button--primary backdrops-create-button"
          onClick={() => setCreateOpen(open => !open)}
          aria-expanded={createOpen}
          aria-controls="create-backdrop-form"
        >
          {createOpen ? 'Close form' : 'Create backdrop'}
        </button>
      </section>

      <div className="backdrops-summary" aria-label="Backdrop library summary">
        <div><strong>{active.length}</strong><span>Active</span></div>
        <div><strong>{archived.length}</strong><span>Archived</span></div>
        <div><strong>{assets.reduce((total, asset) => total + asset.usage_count, 0)}</strong><span>Post uses</span></div>
      </div>

      {createOpen && (
        <form id="create-backdrop-form" className="backdrop-create-form" onSubmit={handleCreate}>
          <div className="backdrop-form-heading">
            <div>
              <h3>Create a recurring backdrop</h3>
              <p>Describe only the setting. Actions, people, and one-off props belong in each post.</p>
            </div>
          </div>
          <div className="backdrop-create-form__grid">
            <div>
              <label htmlFor="new-backdrop-name">Display name (required)</label>
              <input
                id="new-backdrop-name"
                value={newName}
                onChange={event => setNewName(event.target.value)}
                placeholder="Home desk"
                maxLength={80}
                required
              />
              <p className="backdrop-field-note">
                Stable ID: <code>@{identifier || 'backdrop_id'}</code>
              </p>
            </div>
            <div>
              <label htmlFor="new-backdrop-detail">Backdrop description (required)</label>
              <textarea
                id="new-backdrop-detail"
                value={newDetail}
                onChange={event => setNewDetail(event.target.value)}
                placeholder="A warm desk lamp beside a monitor showing an abstract line graph, with a small toolkit on the desk"
                rows={4}
                maxLength={1500}
                required
              />
            </div>
          </div>
          <div className="backdrop-actions">
            <button
              type="submit"
              className="backdrop-button backdrop-button--primary"
              disabled={!identifier || !newDetail.trim() || pending === 'create'}
            >
              {pending === 'create' ? 'Creating…' : 'Create backdrop'}
            </button>
            <button type="button" className="backdrop-button" onClick={() => setCreateOpen(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}

      <div className="backdrops-messages" aria-live="polite">
        {error && <p role="alert" className="backdrops-message backdrops-message--error">{error}</p>}
        {notice && <p className="backdrops-message backdrops-message--success">{notice}</p>}
      </div>

      {loading ? (
        <p role="status" className="backdrops-loading">Loading backdrops…</p>
      ) : (
        <>
          <section className="backdrops-section" aria-labelledby="active-backdrops-heading">
            <div className="backdrops-section__heading">
              <div>
                <h3 id="active-backdrops-heading">Active backdrops</h3>
                <p>Available to the scene agent and in each post’s backdrop selector.</p>
              </div>
            </div>
            {active.length > 0 ? (
              <div className="backdrops-grid">{active.map(renderCard)}</div>
            ) : (
              <div className="backdrops-empty">
                <h4>No active backdrops yet</h4>
                <p>Create one here, or let the scene agent save a recurring setting from a future post.</p>
                <button type="button" className="backdrop-button backdrop-button--primary" onClick={() => setCreateOpen(true)}>
                  Create your first backdrop
                </button>
              </div>
            )}
          </section>

          {archived.length > 0 && (
            <section className="backdrops-section" aria-labelledby="archived-backdrops-heading">
              <div className="backdrops-section__heading">
                <div>
                  <h3 id="archived-backdrops-heading">Archived</h3>
                  <p>Kept for post history, but unavailable for new scenes until restored.</p>
                </div>
              </div>
              <div className="backdrops-grid">{archived.map(renderCard)}</div>
            </section>
          )}
        </>
      )}
    </main>
  )
}
