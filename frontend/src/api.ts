import type {
  Post,
  PostDraft,
  Feedback,
  SceneAsset,
  ImageReadiness,
  RendererStatus,
} from './types'
import { API_BASE, getAccessToken, notifyUnauthorized } from './auth'

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = await getAccessToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(API_BASE + path, { ...opts, headers })
  if (res.status === 401) notifyUnauthorized()
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

  submitAdditionalInfo: (id: string, info: string) =>
    req<Post>(`/posts/${id}/additional-info`, { method: 'POST', body: JSON.stringify({ info }) }),

  acceptDraft: (id: string) => req<Post>(`/posts/${id}/accept-draft`, { method: 'POST' }),

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

  imageReadiness: () => req<ImageReadiness>('/resources/image-readiness'),

  rendererStatus: () => req<RendererStatus>('/resources/renderer-status'),

  generateImage: (id: string, profile: 'full' | 'lightning') =>
    req<Post>(`/posts/${id}/generate-image`, {
      method: 'POST',
      body: JSON.stringify({ profile }),
    }),

  finalize: (id: string) => req<Post>(`/posts/${id}/finalize`, { method: 'POST' }),
  retryStep: (id: string) => req<Post>(`/posts/${id}/retry-step`, { method: 'POST' }),

  listSceneAssets: () => req<SceneAsset[]>('/scene-assets'),

  updateSceneAsset: (name: string, detail_text: string) =>
    req<SceneAsset>(`/scene-assets/${name}`, {
      method: 'PATCH',
      body: JSON.stringify({ detail_text }),
    }),

  deleteSceneAsset: (name: string) =>
    req<{ status: string }>(`/scene-assets/${name}`, { method: 'DELETE' }),
}
