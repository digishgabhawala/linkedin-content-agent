import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { Post } from '../types'

/** Polls GET /posts/{id} while an image task is queued or rendering. */
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
      async function refresh() {
        try {
          setPost(await api.getPost(id))
        } catch {
          // transient network error -- next tick retries
        }
      }
      void refresh()
      intervalRef.current = window.setInterval(refresh, 3000)
    } else {
      stop()
    }

    return stop
  }, [post?.status, post?.id])

  return { post, setPost }
}
