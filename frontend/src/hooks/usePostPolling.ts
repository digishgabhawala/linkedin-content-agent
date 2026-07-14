import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { Post } from '../types'

/** Polls GET /posts/{id} every 3s, but only while status === 'image_queued'
 * (a 15-20 min render, everything else is instant request/response) --
 * pattern verified against code-review-agent's frontend/src/App.tsx. */
export function usePostPolling(initial: Post | null) {
  const [post, setPost] = useState<Post | null>(initial)
  const intervalRef = useRef<number | null>(null)

  useEffect(() => {
    function stop() {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }

    if (post?.status === 'image_queued') {
      const id = post.id
      intervalRef.current = window.setInterval(async () => {
        try {
          setPost(await api.getPost(id))
        } catch {
          // transient network error -- next tick retries
        }
      }, 3000)
    } else {
      stop()
    }

    return stop
  }, [post?.status, post?.id])

  return { post, setPost }
}
