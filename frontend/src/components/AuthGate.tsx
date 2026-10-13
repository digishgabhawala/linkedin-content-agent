import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { API_BASE, authClient, getAccessToken, loadAuthConfig, setUnauthorizedHandler } from '../auth'
import { SessionContext } from '../session'

type GateState =
  | { kind: 'loading' }
  | { kind: 'signedOut'; message?: string }
  | { kind: 'forbidden' }
  | { kind: 'unavailable' }
  | { kind: 'ready'; email: string | null }

async function checkAccess(): Promise<GateState> {
  try {
    const config = await loadAuthConfig()
    if (!config.enabled) return { kind: 'ready', email: null }
    const token = await getAccessToken()
    if (!token) return { kind: 'signedOut' }
    const res = await fetch(`${API_BASE}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
    if (res.status === 401) return { kind: 'signedOut', message: 'Your session expired. Please sign in again.' }
    if (res.status === 403) return { kind: 'forbidden' }
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
        <h1 className="text-lg font-bold text-gray-900">LinkedIn Content Agent</h1>
        {children}
      </div>
    </div>
  )
}

function SignInForm({ message, onSignedIn }: { message?: string; onSignedIn: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const client = authClient()
    if (!client) return
    setBusy(true)
    setError(null)
    const { error: signInError } = await client.auth.signInWithPassword({ email, password })
    setBusy(false)
    if (signInError) setError(signInError.message)
    else onSignedIn()
  }

  return (
    <Card>
      <p className="text-sm text-gray-600">Sign in to continue.</p>
      {message && <p className="rounded-lg bg-amber-50 border border-amber-100 p-2 text-xs text-amber-800">{message}</p>}
      <form onSubmit={submit} className="space-y-3">
        <label className="block text-sm text-gray-700">
          Email
          <input type="email" required autoComplete="username" value={email}
            onChange={e => setEmail(e.target.value)}
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none" />
        </label>
        <label className="block text-sm text-gray-700">
          Password
          <input type="password" required autoComplete="current-password" value={password}
            onChange={e => setPassword(e.target.value)}
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none" />
        </label>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <button type="submit" disabled={busy}
          className="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </Card>
  )
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GateState>({ kind: 'loading' })

  const refresh = useCallback(async () => {
    setState({ kind: 'loading' })
    setState(await checkAccess())
  }, [])

  const signOut = useCallback(async () => {
    await authClient()?.auth.signOut()
    setState({ kind: 'signedOut' })
  }, [])

  useEffect(() => {
    void refresh()
    setUnauthorizedHandler(() =>
      setState({ kind: 'signedOut', message: 'Your session expired. Please sign in again.' }))
    return () => setUnauthorizedHandler(null)
  }, [refresh])

  switch (state.kind) {
    case 'loading':
      return <Card><p className="text-sm text-gray-600">Checking sign-in…</p></Card>
    case 'signedOut':
      return <SignInForm message={state.message} onSignedIn={refresh} />
    case 'forbidden':
      return (
        <Card>
          <p className="text-sm text-gray-700">This account doesn't have access to LinkedIn Content Agent.</p>
          <button onClick={signOut} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">
            Sign out
          </button>
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
        <SessionContext.Provider value={{ email: state.email, signOut }}>
          {children}
        </SessionContext.Provider>
      )
  }
}
