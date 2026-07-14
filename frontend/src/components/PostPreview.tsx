import type { Post } from '../types'

interface Props {
  post: Post
  onFinalize: () => void
  loading: boolean
}

export function PostPreview({ post, onFinalize, loading }: Props) {
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
        <button
          onClick={onFinalize}
          disabled={loading}
          className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
        >
          Mark ready — copy text + image and post manually
        </button>
      )}

      {post.status === 'ready' && (
        <p className="text-xs text-green-700">
          Marked ready. Copy the text above and the image to post on LinkedIn.
        </p>
      )}
    </div>
  )
}
