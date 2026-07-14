import { useState } from 'react'
import type { Post } from '../types'

interface Props {
  post: Post
  onUpdateScene: (scene: string) => void
  onGenerateImage: () => void
  loading: boolean
  error: string | null
}

export function LockAndScene({ post, onUpdateScene, onGenerateImage, loading, error }: Props) {
  const [scene, setScene] = useState(post.scene_instruction ?? '')
  const dirty = scene !== post.scene_instruction

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm space-y-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
        Locked post — derived scene
      </p>

      <pre className="whitespace-pre-wrap font-sans text-sm text-gray-700 leading-relaxed opacity-80">
        {post.post_text}
      </pre>

      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          Image scene (edit before rendering — this is what the character will be doing)
        </label>
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
            Save scene edit
          </button>
        )}
      </div>

      {error && (
        <p className="rounded-lg bg-red-50 border border-red-100 p-2 text-xs text-red-700">
          {error}
        </p>
      )}

      <button
        onClick={onGenerateImage}
        disabled={loading || dirty}
        className="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? 'Starting render…' : 'Generate image (15-20 min)'}
      </button>
      {dirty && (
        <p className="text-xs text-amber-600">Save your scene edit before generating.</p>
      )}
    </div>
  )
}
