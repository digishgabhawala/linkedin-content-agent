import { useEffect, useState } from 'react'
import type { Post } from '../types'
import { BackdropSelector } from './BackdropSelector'

interface Props {
  post: Post
  onUpdateScene: (scene: string) => void
  onBackdropChange: (name: string | null) => void
  onUseLatestBackdrop: () => void
  onGenerateImage: () => void
  loading: boolean
  error: string | null
}

export function LockAndScene({ post, onUpdateScene, onBackdropChange, onUseLatestBackdrop, onGenerateImage, loading, error }: Props) {
  const [scene, setScene] = useState(post.scene_instruction ?? '')
  const dirty = scene !== (post.scene_instruction ?? '')

  useEffect(() => {
    setScene(post.scene_instruction ?? '')
  }, [post.scene_instruction])

  return (
    <section className="post-panel post-panel--scene" aria-labelledby={`scene-${post.id}-heading`}>
      <p id={`scene-${post.id}-heading`} className="post-panel__eyebrow">
        Locked post — derived scene
      </p>

      <pre className="post-copy post-copy--muted">
        {post.post_text}
      </pre>

      <BackdropSelector
        post={post}
        loading={loading}
        onChange={onBackdropChange}
        onUseLatest={onUseLatestBackdrop}
      />

      <div className="post-field">
        <label htmlFor={`scene-${post.id}-details`}>
          Image scene details (advanced)
        </label>
        <textarea
          id={`scene-${post.id}-details`}
          rows={4}
          value={scene}
          onChange={e => setScene(e.target.value)}
        />
        {dirty && (
          <button
            type="button"
            onClick={() => onUpdateScene(scene)}
            className="post-button post-button--secondary post-field__action"
          >
            Save scene edit
          </button>
        )}
      </div>

      {error && (
        <p className="post-message post-message--danger" role="alert">
          {error}
        </p>
      )}

      <button
        type="button"
        onClick={onGenerateImage}
        disabled={loading || dirty}
        className="post-button post-button--primary post-button--wide"
      >
        {loading ? 'Checking memory…' : 'Generate image'}
      </button>
      {dirty && (
        <p className="post-message post-message--warning">Save your scene edit before generating.</p>
      )}
    </section>
  )
}
