import { createClient, type SupabaseClient } from '@supabase/supabase-js'

// Browser side of the login (backend: app/auth.py). The Supabase URL and
// browser-safe key come from the backend, so nothing is baked into the
// build. Default session storage: apps on the same origin share one login.
export const API_BASE = '/api/linkedin'

export interface AuthConfig {
  enabled: boolean
  supabase_url: string | null
  supabase_publishable_key: string | null
}

let client: SupabaseClient | null = null
let unauthorizedHandler: (() => void) | null = null
let refusedHandler: ((reason: AccountRefusal) => void) | null = null

// Why the backend refuses a signed-in account (403 + `reason`, app/auth.py).
export const ACCOUNT_REFUSALS = ['pending', 'rejected', 'suspended', 'no_membership'] as const
export type AccountRefusal = (typeof ACCOUNT_REFUSALS)[number]

export function isAccountRefusal(reason: unknown): reason is AccountRefusal {
  return typeof reason === 'string' && (ACCOUNT_REFUSALS as readonly string[]).includes(reason)
}

export async function loadAuthConfig(): Promise<AuthConfig> {
  const res = await fetch(`${API_BASE}/auth/config`, { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`Auth configuration unavailable: ${res.status}`)
  const config: AuthConfig = await res.json()
  if (config.enabled && !client) {
    client = createClient(config.supabase_url!, config.supabase_publishable_key!, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
    })
  }
  return config
}

export function authClient(): SupabaseClient | null {
  return client
}

// Read on every request, so a refreshed token is always the one sent.
export async function getAccessToken(): Promise<string | null> {
  if (!client) return null
  const { data } = await client.auth.getSession()
  return data.session?.access_token ?? null
}

export function setUnauthorizedHandler(handler: (() => void) | null) {
  unauthorizedHandler = handler
}

export function notifyUnauthorized() {
  unauthorizedHandler?.()
}

// A 403 account refusal on any API call mid-session (approval revoked,
// account suspended): AuthGate swaps the whole app for its refusal screen.
export function setRefusedHandler(handler: ((reason: AccountRefusal) => void) | null) {
  refusedHandler = handler
}

export function notifyRefused(reason: AccountRefusal) {
  refusedHandler?.(reason)
}
