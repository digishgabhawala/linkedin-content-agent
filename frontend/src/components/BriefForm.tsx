import { useState } from 'react'

interface Props {
  onSubmit: (brief: string) => void
  loading: boolean
}

export function BriefForm({ onSubmit, loading }: Props) {
  const [brief, setBrief] = useState('')

  function submit() {
    if (!brief.trim() || loading) return
    onSubmit(brief.trim())
  }

  return (
    <div className="space-y-3">
      <label className="block text-sm font-medium text-gray-700">
        What did you work on?
      </label>
      <textarea
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
        rows={4}
        placeholder="e.g. fixed an OOM crash in the image pipeline by switching to low-ram mode, zero speed cost"
        value={brief}
        onChange={e => setBrief(e.target.value)}
        disabled={loading}
      />
      <button
        onClick={submit}
        disabled={loading || !brief.trim()}
        className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? 'Starting…' : 'Start a post'}
      </button>
    </div>
  )
}
