import { useEffect, useState } from 'react'
import { api } from '../api'
import type { SceneAsset } from '../types'

interface Props {
  onInsert: (ref: string) => void
}

// Inserts a short "@name" reference, not the full detail text -- the
// backend expands it to the asset's current detail_text only at render
// time (see post_service.expand_scene_refs), so the saved scene stays
// short and readable, and an asset edited later still applies here.
export function BackdropInsertDropdown({ onInsert }: Props) {
  const [assets, setAssets] = useState<SceneAsset[]>([])

  useEffect(() => {
    api.listSceneAssets().then(setAssets).catch(() => {})
  }, [])

  if (assets.length === 0) return null

  return (
    <select
      value=""
      onChange={e => {
        if (e.target.value) onInsert(`@${e.target.value}`)
        e.target.value = ''
      }}
      className="rounded-lg border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
      title="Append a backdrop reference (e.g. @office) to the end of the prompt above"
    >
      <option value="" disabled>Insert backdrop ▾</option>
      {assets.map(a => (
        <option key={a.name} value={a.name}>@{a.name}</option>
      ))}
    </select>
  )
}
