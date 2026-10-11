import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { Post } from '../types'

/** Polls GET /posts/{id} while a step is in flight. Each poll is also what
 * advances the post to its next step (see backend services/steps.py) -- so
 * if no one has the post open, it pauses between steps (known limitation). */
export function usePostPolling(initial: Post | null) {
  const [post, setPost] = useState<Post | null>(initial)
  const timerRef = useRef<number | null>(null)
  const pollId = post && (post.active_step || post.status === 'image_queued') ? post.id : null

  useEffect(() => {
    if (pollId === null) return
    let cancelled = false
    // Next poll is scheduled only after the previous one finished: a slow
    // status check (it may advance the post over the network) never piles up.
    async function refresh() {
      try {
        const next = await api.getPost(pollId as string)
        if (!cancelled) setPost(next)
      } catch {
        // transient network error -- next tick retries
      }
      if (!cancelled) timerRef.current = window.setTimeout(refresh, 3000)
    }
    void refresh()
    return () => {
      cancelled = true
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [pollId])

  return { post, setPost }
}
