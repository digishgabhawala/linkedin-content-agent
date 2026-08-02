import { useEffect, useState } from 'react'
import { api } from '../api'
import type { SceneAsset } from '../types'

export function SceneAssetsPanel() {
  const [assets, setAssets] = useState<SceneAsset[]>([])
  const [open, setOpen] = useState(false)
  const [editingName, setEditingName] = useState<string | null>(null)
  const [editText, setEditText] = useState('')

  async function refresh() {
    setAssets(await api.listSceneAssets())
  }

  useEffect(() => {
    if (open) refresh()
  }, [open])

  async function handleSave(name: string) {
    await api.updateSceneAsset(name, editText)
    setEditingName(null)
    await refresh()
  }

  async function handleDelete(name: string) {
    if (!window.confirm(
      `Forget the "${name}" backdrop? Posts that already used it keep their saved image/prompt ` +
      `unchanged -- this only means the NEXT post whose scene proposes "${name}" again will get a ` +
      `freshly generated description instead of reusing this one.`
    )) return
    await api.deleteSceneAsset(name)
    await refresh()
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold uppercase tracking-wide text-gray-500"
      >
        <span>Recurring backdrops</span>
        <span>{open ? '−' : '+'}</span>
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-2">
          {assets.length === 0 && (
            <p className="text-xs text-gray-400">
              None yet — a backdrop is created the first time a scene names one (e.g. "office").
            </p>
          )}
          {assets.map(a => (
            <div key={a.name} className="rounded-lg border border-purple-100 bg-purple-50 p-2 space-y-1">
              <p className="text-xs font-semibold text-purple-900">{a.name}</p>
              {editingName === a.name ? (
                <>
                  <textarea
                    className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                    rows={3}
                    value={editText}
                    onChange={e => setEditText(e.target.value)}
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleSave(a.name)}
                      className="text-xs text-purple-700 underline hover:text-purple-900"
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingName(null)}
                      className="text-xs text-gray-500 underline hover:text-gray-700"
                    >
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <p className="text-xs text-purple-800">{a.detail_text}</p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => { setEditingName(a.name); setEditText(a.detail_text) }}
                      className="text-xs text-purple-600 underline hover:text-purple-800"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDelete(a.name)}
                      className="text-xs text-purple-600 underline hover:text-purple-800"
                    >
                      Forget
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
