import { createContext, useContext } from 'react'

export interface Session {
  email: string | null // null when login is disabled (local development)
  signOut: () => void
}

export const SessionContext = createContext<Session>({ email: null, signOut: () => {} })

export function useSession(): Session {
  return useContext(SessionContext)
}
