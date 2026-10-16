import type {
  Post,
  PostDraft,
  Feedback,
  SceneAsset,
  SceneAssetVersion,
  ImageReadiness,
  RendererStatus,
  Character,
  CharacterCardInput,
  HeroGenerationRun,
  LockHeroCandidateResult,
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

  useLatestBackdrop: (id: string) =>
    req<Post>(`/posts/${id}/scene/use-latest-backdrop`, { method: 'POST' }),

  imageReadiness: () => req<ImageReadiness>('/resources/image-readiness'),

  rendererStatus: () => req<RendererStatus>('/resources/renderer-status'),

  generateImage: (id: string, profile: 'full' | 'lightning') =>
    req<Post>(`/posts/${id}/generate-image`, {
      method: 'POST',
      body: JSON.stringify({ profile }),
    }),

  finalize: (id: string) => req<Post>(`/posts/${id}/finalize`, { method: 'POST' }),
  retryStep: (id: string) => req<Post>(`/posts/${id}/retry-step`, { method: 'POST' }),

  listSceneAssets: (includeArchived = false) =>
    req<SceneAsset[]>(`/scene-assets${includeArchived ? '?include_archived=true' : ''}`),

  createSceneAsset: (display_name: string, detail_text: string) =>
    req<SceneAsset>('/scene-assets', {
      method: 'POST',
      body: JSON.stringify({ display_name, detail_text }),
    }),

  updateSceneAsset: (name: string, display_name: string, detail_text: string) =>
    req<SceneAsset>(`/scene-assets/${encodeURIComponent(name)}`, {
      method: 'PATCH',
      body: JSON.stringify({ display_name, detail_text }),
    }),

  listSceneAssetVersions: (name: string) =>
    req<SceneAssetVersion[]>(`/scene-assets/${encodeURIComponent(name)}/versions`),

  archiveSceneAsset: (name: string) =>
    req<SceneAsset>(`/scene-assets/${encodeURIComponent(name)}/archive`, { method: 'POST' }),

  unarchiveSceneAsset: (name: string) =>
    req<SceneAsset>(`/scene-assets/${encodeURIComponent(name)}/unarchive`, { method: 'POST' }),

  restoreSceneAssetVersion: (name: string, version: number) =>
    req<SceneAsset>(
      `/scene-assets/${encodeURIComponent(name)}/versions/${version}/restore`,
      { method: 'POST' },
    ),

  updatePostBackdrop: (id: string, scene_asset_name: string | null) =>
    req<Post>(`/posts/${id}/backdrop`, {
      method: 'PATCH',
      body: JSON.stringify({ scene_asset_name }),
    }),

  createCharacter: (character: CharacterCardInput) =>
    req<Character>('/characters', {
      method: 'POST',
      body: JSON.stringify(character),
    }),

  listCharacters: () => req<Character[]>('/characters'),

  getCharacter: (characterId: string) =>
    req<Character>(`/characters/${encodeURIComponent(characterId)}`),

  startHeroGeneration: (
    characterId: string,
    request: { candidate_count: number; base_seed?: number; profile: 'full' | 'lightning' },
  ) =>
    req<HeroGenerationRun>(
      `/characters/${encodeURIComponent(characterId)}/hero-generations`,
      { method: 'POST', body: JSON.stringify(request) },
    ),

  listHeroGenerations: (characterId: string) =>
    req<HeroGenerationRun[]>(
      `/characters/${encodeURIComponent(characterId)}/hero-generations`,
    ),

  getHeroGeneration: (characterId: string, runId: string) =>
    req<HeroGenerationRun>(
      `/characters/${encodeURIComponent(characterId)}/hero-generations/${encodeURIComponent(runId)}`,
    ),

  lockHeroCandidate: (characterId: string, candidateId: string) =>
    req<LockHeroCandidateResult>(
      `/characters/${encodeURIComponent(characterId)}/hero-candidates/${encodeURIComponent(candidateId)}/lock`,
      { method: 'POST' },
    ),
}
