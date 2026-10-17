import { createContext, useContext } from 'react'
import { authClient } from './auth'

export interface Session {
  email: string | null // null when login is disabled (local development)
  signOut: () => void
}

// Shared sign-in page of the suite (parent site). Only a missing or rejected
// session goes there -- never a refused account, which would loop back.
export const LOGIN_URL = '/login?next=' + encodeURIComponent('/linkedin')

/** Sign out of the shared Supabase session and go to the suite's /login.
 * With login disabled (local development) there is nothing to sign out of. */
export async function signOut(): Promise<void> {
  const client = authClient()
  if (!client) return
  await client.auth.signOut()
  window.location.assign('/login')
}

export const SessionContext = createContext<Session>({ email: null, signOut: () => {} })

export function useSession(): Session {
  return useContext(SessionContext)
}
