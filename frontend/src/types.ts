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
  image_worker_id: string | null
  image_progress_stage: string | null
  image_progress_message: string | null
  image_progress_updated_at: string | null
  is_worker_lost: boolean
  image_failure_kind: 'corrupt_output' | 'insufficient_memory' | null
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

// Measured and reported by the image worker (which may be another machine).
// source 'unknown' = no worker memory report yet; enough_memory is then true
// and the worker itself refuses a Full render that can't fit.
export interface ImageReadiness {
  source: 'worker' | 'unknown'
  worker_name: string | null
  available_gb: number | null
  recommended_gb: number | null
  enough_memory: boolean
  top_consumers: MemoryConsumer[]
}

export interface WorkerDetails {
  memory?: { available_gb?: number; required_gb?: Record<string, number> }
  comfyui?: { state?: string; managed?: boolean }
  [key: string]: unknown
}

export interface RendererWorker {
  id: string
  name: string
  state: 'idle' | 'busy' | string
  current_task_id: string | null
  last_heartbeat_at: string | null
  details: WorkerDetails
}

export interface RendererStatus {
  reachable: boolean
  online: boolean
  online_count: number
  busy_count: number
  last_seen_at: string | null
  message: string
  workers: RendererWorker[]
}
