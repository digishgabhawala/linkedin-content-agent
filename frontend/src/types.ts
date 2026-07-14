export type PostStatus =
  | 'clarifying'
  | 'drafting'
  | 'locked'
  | 'image_queued'
  | 'image_ready'
  | 'image_failed'
  | 'ready'

export interface Post {
  id: string
  character_id: string
  brief: string
  status: PostStatus
  pending_question: string | null
  post_text: string | null
  draft_version: number
  scene_instruction: string | null
  seed: number | null
  image_url: string | null
  has_final_image: boolean
  image_job_error: string | null
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

export interface Feedback {
  id: string
  stage: string
  user_note: string
  post_text_snippet: string | null
  created_at: string | null
}
