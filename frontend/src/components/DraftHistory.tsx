import { useEffect, useState } from 'react'
import { api } from '../api'
import type { PostDraft } from '../types'

interface Props {
  postId: string
  currentVersion: number
}

export function DraftHistory({ postId, currentVersion }: Props) {
  const [drafts, setDrafts] = useState<PostDraft[]>([])
  const [open, setOpen] = useState(false)

  useEffect(() => {
    api.getDrafts(postId).then(setDrafts).catch(() => {})
  }, [postId, currentVersion])

  if (drafts.length <= 1) return null

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <button
        onClick={() => setOpen(o => !o)}
        className="text-xs font-semibold uppercase tracking-wide text-gray-500"
      >
        Draft history ({drafts.length}) {open ? '▲' : '▼'}
      </button>
      {open && (
        <div className="mt-3 space-y-3">
          {[...drafts].reverse().map(d => (
            <div key={d.id} className="rounded-lg border border-gray-100 p-3">
              <div className="flex items-center justify-between text-xs text-gray-500">
                <span className="font-medium">
                  v{d.version} · {d.generated_by}
                  {d.version === currentVersion && (
                    <span className="ml-2 rounded bg-blue-100 px-1.5 py-0.5 text-blue-700">
                      current
                    </span>
                  )}
                </span>
                {d.created_at && <span>{new Date(d.created_at).toLocaleTimeString()}</span>}
              </div>
              {d.user_instruction && (
                <p className="mt-1 text-xs italic text-gray-500">"{d.user_instruction}"</p>
              )}
              <p className="mt-1 whitespace-pre-wrap text-xs text-gray-600 line-clamp-3">
                {d.post_text}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
