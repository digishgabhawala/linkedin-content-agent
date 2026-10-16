import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Post, SceneAsset } from '../types'

interface Props {
  post: Post
  loading: boolean
  onChange: (name: string | null) => void
  onUseLatest: () => void
}

export function BackdropSelector({ post, loading, onChange, onUseLatest }: Props) {
  const [assets, setAssets] = useState<SceneAsset[]>([])
  const [loadError, setLoadError] = useState(false)

  useEffect(() => {
    api.listSceneAssets()
      .then(next => {
        setAssets(next)
        setLoadError(false)
      })
      .catch(() => setLoadError(true))
  }, [])

  const currentIsArchived = Boolean(
    post.scene_asset_name && !assets.some(asset => asset.name === post.scene_asset_name),
  )

  return (
    <section className="post-backdrop-selector" aria-labelledby={`post-${post.id}-backdrop-heading`}>
      <div className="post-backdrop-selector__heading">
        <div>
          <h3 id={`post-${post.id}-backdrop-heading`}>Recurring backdrop</h3>
          <p>Choose a saved setting, or let this scene stand on its own.</p>
        </div>
        <a href="#backdrops">Manage backdrops</a>
      </div>
      <div className="post-backdrop-selector__control">
        <label htmlFor={`post-${post.id}-backdrop`}>Backdrop for this image</label>
        <select
          id={`post-${post.id}-backdrop`}
          value={post.scene_asset_name ?? ''}
          onChange={event => onChange(event.target.value || null)}
          disabled={loading || loadError}
        >
          <option value="">Scene-derived · no saved backdrop</option>
          {currentIsArchived && post.scene_asset_name && (
            <option value={post.scene_asset_name} disabled>
              {post.scene_asset_display_name ?? post.scene_asset_name} · archived
            </option>
          )}
          {assets.map(asset => (
            <option key={asset.name} value={asset.name}>
              {asset.display_name} · v{asset.current_version}
            </option>
          ))}
        </select>
      </div>
      {loadError && (
        <p role="alert" className="post-backdrop-selector__error">
          Saved backdrops could not be loaded. Your current scene is unchanged.
        </p>
      )}
      {post.scene_asset_name && (
        <div className="post-backdrop-selector__version">
          <span>
            This post is pinned to version {post.scene_asset_version ?? 'unknown'}.
            {currentIsArchived && ' The backdrop is archived.'}
          </span>
          {!post.scene_asset_is_latest && post.scene_asset_latest_version && (
            <button type="button" onClick={onUseLatest} disabled={loading}>
              Use latest version {post.scene_asset_latest_version}
            </button>
          )}
        </div>
      )}
    </section>
  )
}
