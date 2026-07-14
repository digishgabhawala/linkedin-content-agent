import type { Post, PostDraft, Feedback } from './types'

const BASE = '/api'

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? `Request failed: ${res.status}`)
  }
  return res.json()
}

export const api = {
  createPost: (brief: string, character_id?: string) =>
    req<Post>('/posts', { method: 'POST', body: JSON.stringify({ brief, character_id }) }),

  listPosts: () => req<Post[]>('/posts'),

  getPost: (id: string) => req<Post>(`/posts/${id}`),

  clarify: (id: string, answer: string) =>
    req<Post>(`/posts/${id}/clarify`, { method: 'POST', body: JSON.stringify({ answer }) }),

  redraft: (id: string) => req<Post>(`/posts/${id}/draft`, { method: 'POST' }),

  regenerate: (id: string, instruction: string) =>
    req<Post>(`/posts/${id}/regenerate`, {
      method: 'POST',
      body: JSON.stringify({ instruction }),
    }),

  getDrafts: (id: string) => req<PostDraft[]>(`/posts/${id}/drafts`),

  addFeedback: (id: string, stage: string, user_note: string, post_text_snippet?: string) =>
    req<Feedback>(`/posts/${id}/feedback`, {
      method: 'POST',
      body: JSON.stringify({ stage, user_note, post_text_snippet }),
    }),

  getFeedback: (id: string) => req<Feedback[]>(`/posts/${id}/feedback`),

  lock: (id: string) => req<Post>(`/posts/${id}/lock`, { method: 'POST' }),

  updateScene: (id: string, scene_instruction: string) =>
    req<Post>(`/posts/${id}/scene`, {
      method: 'PATCH',
      body: JSON.stringify({ scene_instruction }),
    }),

  generateImage: (id: string) => req<Post>(`/posts/${id}/generate-image`, { method: 'POST' }),

  finalize: (id: string) => req<Post>(`/posts/${id}/finalize`, { method: 'POST' }),
}
