import { useState } from 'react'
import type { Post } from '../types'
import { BackdropInsertDropdown } from './BackdropInsertDropdown'

interface Props {
  post: Post
  onFinalize: () => void
  onRegenerateImage: () => void
  onUpdateScene: (scene: string) => void
  onForgetAsset: (name: string) => void
  loading: boolean
}

export function PostPreview({ post, onFinalize, onRegenerateImage, onUpdateScene, onForgetAsset, loading }: Props) {
  const [scene, setScene] = useState(post.scene_instruction ?? '')
  const dirty = scene !== (post.scene_instruction ?? '')

  function handleRegenerate() {
    if (window.confirm(
      'Regenerate a new image for this post? This replaces the current image ' +
      '(a fresh 15-30 min render, same scene instruction, new seed) -- the ' +
      'current one will be overwritten once the new render finishes.'
    )) {
      onRegenerateImage()
    }
  }
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm space-y-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
        {post.status === 'ready' ? 'Ready to post' : 'Image ready — review before posting'}
      </p>

      {post.image_url && (
        <img
          src={post.image_url}
          alt="Generated character illustration"
          className="w-full max-w-sm rounded-lg border border-gray-200"
        />
      )}

      <pre className="whitespace-pre-wrap font-sans text-sm text-gray-800 leading-relaxed">
        {post.post_text}
      </pre>

      {post.status === 'image_ready' && post.scene_asset_name && (
        <div className="flex items-center justify-between rounded-lg bg-purple-50 border border-purple-100 px-3 py-2">
          <p className="text-xs text-purple-800">
            Uses recurring backdrop: <span className="font-semibold">{post.scene_asset_name}</span>
            {' '}— reused verbatim from other posts, not regenerated fresh each time.
          </p>
          <button
            onClick={() => onForgetAsset(post.scene_asset_name!)}
            className="text-xs text-purple-600 underline hover:text-purple-800"
            title="Delete this backdrop so future posts get a freshly generated one -- does not change this post's saved image or prompt"
          >
            Forget this backdrop
          </button>
        </div>
      )}

      {post.status === 'image_ready' && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="block text-xs font-medium text-gray-600">
              Image prompt used — edit for a small targeted change (e.g. drop one object, keep
              everything else), then regenerate
            </label>
            <BackdropInsertDropdown onInsert={detail => setScene(s => s ? `${s}, ${detail}` : detail)} />
          </div>
          <textarea
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
            rows={2}
            value={scene}
            onChange={e => setScene(e.target.value)}
          />
          {dirty && (
            <button
              onClick={() => onUpdateScene(scene)}
              className="mt-2 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
            >
              Save prompt edit
            </button>
          )}
        </div>
      )}

      {post.status === 'image_ready' && (
        <div className="flex gap-3">
          <button
            onClick={onFinalize}
            disabled={loading || dirty}
            className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            Mark ready — copy text + image and post manually
          </button>
          <button
            onClick={handleRegenerate}
            disabled={loading || dirty}
            className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Regenerate image
          </button>
        </div>
      )}
      {post.status === 'image_ready' && dirty && (
        <p className="text-xs text-amber-600">Save your prompt edit before finalizing or regenerating.</p>
      )}

      {post.status === 'ready' && (
        <p className="text-xs text-green-700">
          Marked ready. Copy the text above and the image to post on LinkedIn.
        </p>
      )}
    </div>
  )
}
