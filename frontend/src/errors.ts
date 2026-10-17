// An API error the UI can act on: the HTTP status plus the backend's
// machine-readable reason (e.g. "profile_required", "character_required").
export class ApiError extends Error {
  status: number
  reason: string | null

  constructor(message: string, status: number, reason: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.reason = reason
  }
}
