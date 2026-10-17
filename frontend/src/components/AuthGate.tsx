import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { API_BASE, authClient, getAccessToken, loadAuthConfig, setUnauthorizedHandler } from '../auth'
import { LOGIN_URL, SessionContext, signOut } from '../session'
import { SuiteBrand } from './SuiteBrand'

// Sign-in itself happens on the suite's shared /login page. This gate only
// decides: no session (or one the backend rejects) -> /login; a signed-in
// account the backend refuses -> a message, never a redirect (/login would
// send the user straight back here).
type Refusal = 'pending' | 'rejected' | 'suspended' | 'no_membership'

type GateState =
  | { kind: 'loading' }
  | { kind: 'redirecting' }
  | { kind: 'refused'; reason: Refusal }
  | { kind: 'unavailable' }
  | { kind: 'ready'; email: string | null }

const REFUSALS: Record<Refusal, string> = {
  pending: 'Your account is waiting for approval.',
  rejected: 'Your account was not approved.',
  suspended: 'Your account is suspended.',
  no_membership: 'Your account does not have access to LinkedIn Content Agent.',
}

let redirecting = false // one navigation only: a second one would abort the first

/** Drop the rejected session locally (so /login doesn't bounce back), then go there. */
async function goToLogin(clearSession: boolean): Promise<GateState> {
  if (clearSession) await authClient()?.auth.signOut({ scope: 'local' }).catch(() => undefined)
  if (!redirecting) {
    redirecting = true
    window.location.replace(LOGIN_URL)
  }
  return { kind: 'redirecting' }
}

async function checkAccess(): Promise<GateState> {
  try {
    const config = await loadAuthConfig()
    if (!config.enabled) return { kind: 'ready', email: null }
    const token = await getAccessToken()
    if (!token) return goToLogin(false)
    const res = await fetch(`${API_BASE}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
    if (res.status === 401) return goToLogin(true)
    if (res.status === 403) {
      const body = await res.json().catch(() => ({}))
      const reason = (body.reason in REFUSALS ? body.reason : 'no_membership') as Refusal
      return { kind: 'refused', reason }
    }
    if (!res.ok) return { kind: 'unavailable' }
    return { kind: 'ready', email: (await res.json()).email }
  } catch {
    return { kind: 'unavailable' }
  }
}

function Card({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-xl border border-gray-200 bg-white p-6 shadow-sm space-y-4">
        <SuiteBrand />
        <div>
          <p className="font-mono text-xs text-[#4946c7]">AI Bharatiyaa account</p>
          <h1 className="text-lg font-bold text-gray-900">LinkedIn Content Agent</h1>
        </div>
        {children}
      </div>
    </div>
  )
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GateState>({ kind: 'loading' })

  const refresh = useCallback(async () => {
    setState({ kind: 'loading' })
    setState(await checkAccess())
  }, [])

  useEffect(() => {
    void refresh()
    setUnauthorizedHandler(() => {
      void goToLogin(true).then(setState)
    })
    return () => setUnauthorizedHandler(null)
  }, [refresh])

  switch (state.kind) {
    case 'loading':
      return <Card><p className="text-sm text-gray-600">Checking sign-in…</p></Card>
    case 'redirecting':
      return <Card><p className="text-sm text-gray-600">Taking you to sign-in…</p></Card>
    case 'refused':
      return (
        <Card>
          <p role="status" className="text-sm text-gray-700">{REFUSALS[state.reason]}</p>
          <div className="flex flex-wrap items-center gap-3">
            <a href="/account" className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
              Your account
            </a>
            <button onClick={() => void signOut()} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">
              Sign out
            </button>
          </div>
        </Card>
      )
    case 'unavailable':
      return (
        <Card>
          <p className="text-sm text-gray-700">Sign-in is unavailable right now. Try again shortly.</p>
          <button onClick={refresh} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
            Retry
          </button>
        </Card>
      )
    case 'ready':
      return (
        <SessionContext.Provider value={{ email: state.email, signOut: () => void signOut() }}>
          {children}
        </SessionContext.Provider>
      )
  }
}
