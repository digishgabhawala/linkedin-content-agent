import type { Post } from '../types'

interface Props {
  post: Post
  onFinalize: () => void
  onRegenerateImage: () => void
  loading: boolean
}

export function PostPreview({ post, onFinalize, onRegenerateImage, loading }: Props) {
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

      {post.status === 'image_ready' && (
        <div className="flex gap-3">
          <button
            onClick={onFinalize}
            disabled={loading}
            className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            Mark ready — copy text + image and post manually
          </button>
          <button
            onClick={handleRegenerate}
            disabled={loading}
            className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Regenerate image
          </button>
        </div>
      )}

      {post.status === 'ready' && (
        <p className="text-xs text-green-700">
          Marked ready. Copy the text above and the image to post on LinkedIn.
        </p>
      )}
    </div>
  )
}
