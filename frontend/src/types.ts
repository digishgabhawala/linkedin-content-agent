export type PostStatus =
  | 'clarifying'
  | 'needs_input'
  | 'drafting'
  | 'locked'
  | 'image_queued'
  | 'image_ready'
  | 'image_failed'
  | 'ready'

export interface PillarScore {
  score: number
  reason: string
}

export interface Post {
  id: string
  character_id: string
  brief: string
  status: PostStatus
  pending_question: string | null
  clarify_transcript: { question: string; answer: string | null }[]
  post_text: string | null
  draft_version: number
  category: string | null
  gate_scores: Record<string, PillarScore>
  pillar_scores: Record<string, PillarScore>
  weighted_score: number | null
  recalibration_count: number
  escalation_reason: string | null
  scene_instruction: string | null
  scene_asset_name: string | null
  seed: number | null
  image_url: string | null
  has_final_image: boolean
  image_job_error: string | null
  image_queue_status: 'queued' | 'claimed' | 'done' | 'failed' | null
  image_claimed_at: string | null
  is_queue_delayed: boolean
  is_stalled: boolean
  image_started_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface PostDraft {
  id: string
  version: number
  post_text: string
  generated_by: string
  user_instruction: string | null
  created_at: string | null
}

export interface SceneAsset {
  name: string
  detail_text: string
  created_at: string | null
  updated_at: string | null
}

export interface Feedback {
  id: string
  stage: string
  user_note: string
  post_text_snippet: string | null
  created_at: string | null
}

export interface MemoryConsumer {
  name: string
  memory_gb: number
}

export interface ImageReadiness {
  available_bytes: number
  available_gb: number
  recommended_gb: number
  enough_memory: boolean
  top_consumers: MemoryConsumer[]
}

export interface LocalRendererStatus {
  online: boolean
  worker_running: boolean
  comfyui_online: boolean
  message: string
}
