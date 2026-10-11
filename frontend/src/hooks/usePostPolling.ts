import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { Post } from '../types'

/** Polls GET /posts/{id} while a step is in flight. Each poll is also what
 * advances the post to its next step (see backend services/steps.py) -- so
 * if no one has the post open, it pauses between steps (known limitation). */
export function usePostPolling(initial: Post | null) {
  const [post, setPost] = useState<Post | null>(initial)
  const intervalRef = useRef<number | null>(null)
  const pollId = post && (post.active_step || post.status === 'image_queued') ? post.id : null

  useEffect(() => {
    if (pollId === null) return
    async function refresh() {
      try {
        setPost(await api.getPost(pollId as string))
      } catch {
        // transient network error -- next tick retries
      }
    }
    void refresh()
    intervalRef.current = window.setInterval(refresh, 3000)
    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [pollId])

  return { post, setPost }
}
