import { useEffect, useState } from 'react'
import type { Post } from '../types'
import { BackdropSelector } from './BackdropSelector'

interface Props {
  post: Post
  onFinalize: () => void
  onRegenerateImage: () => void
  onUpdateScene: (scene: string) => void
  onBackdropChange: (name: string | null) => void
  onUseLatestBackdrop: () => void
  loading: boolean
}

export function PostPreview({ post, onFinalize, onRegenerateImage, onUpdateScene, onBackdropChange, onUseLatestBackdrop, loading }: Props) {
  const [scene, setScene] = useState(post.scene_instruction ?? '')
  const dirty = scene !== (post.scene_instruction ?? '')

  useEffect(() => {
    setScene(post.scene_instruction ?? '')
  }, [post.scene_instruction])

  function handleRegenerate() {
    if (window.confirm(
      'Regenerate a new image for this post? This replaces the current image ' +
      '(same scene instruction, new seed; render time depends on memory and mode) -- the ' +
      'current one will be overwritten once the new render finishes.'
    )) {
      onRegenerateImage()
    }
  }
  return (
    <section className="post-panel post-panel--preview" aria-labelledby={`preview-${post.id}-heading`}>
      <p id={`preview-${post.id}-heading`} className="post-panel__eyebrow">
        {post.status === 'ready' ? 'Ready to post' : 'Image ready — review before posting'}
      </p>

      {post.image_url && (
        <div className="post-preview__media">
          <img
            src={post.image_url}
            alt="Generated character illustration"
          />
        </div>
      )}

      <pre className="post-copy">
        {post.post_text}
      </pre>

      {post.status === 'image_ready' && (
        <BackdropSelector
          post={post}
          loading={loading}
          onChange={onBackdropChange}
          onUseLatest={onUseLatestBackdrop}
        />
      )}

      {post.status === 'image_ready' && (
        <div className="post-field">
          <label htmlFor={`preview-${post.id}-prompt`}>
            Image prompt details (advanced) — edit for a targeted change, then regenerate
          </label>
          <textarea
            id={`preview-${post.id}-prompt`}
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
              Save prompt edit
            </button>
          )}
        </div>
      )}

      {post.status === 'image_ready' && (
        <div className="post-actions post-actions--separated">
          <button
            type="button"
            onClick={onFinalize}
            disabled={loading || dirty}
            className="post-button post-button--success post-actions__primary"
          >
            Mark ready to post
          </button>
          <button
            type="button"
            onClick={handleRegenerate}
            disabled={loading || dirty}
            className="post-button post-button--secondary"
          >
            Regenerate image
          </button>
        </div>
      )}
      {post.status === 'image_ready' && dirty && (
        <p className="post-message post-message--warning">Save your prompt edit before finalizing or regenerating.</p>
      )}

      {post.status === 'ready' && (
        <p className="post-message post-message--success">
          Marked ready. Copy the text above and the image to post on LinkedIn.
        </p>
      )}
    </section>
  )
}
