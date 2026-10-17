import { expect, test, type Page } from '@playwright/test'

// Login on (mocked): signed-out users go to the shared /login; refused users
// see a message and are never bounced (that would loop back from /login).
const SUPA = 'https://proj.supabase.co'

async function enableAuth(page: Page, me: { status: number; body: unknown }, signedIn = true) {
  await page.route('**/api/linkedin/auth/config', r => r.fulfill({ json: {
    enabled: true, supabase_url: SUPA, supabase_publishable_key: 'pk' } }))
  await page.route('**/api/linkedin/auth/me', r => r.fulfill({ status: me.status, json: me.body }))
  await page.route(`${SUPA}/**`, r => r.fulfill({ json: {} }))
  await page.route('**/login**', r => r.fulfill({ body: 'login stub', contentType: 'text/html' }))
  if (signedIn) {
    await page.addInitScript(([s]) => localStorage.setItem('sb-proj-auth-token', s), [JSON.stringify({
      access_token: 'h.e30.s', token_type: 'bearer', expires_in: 3600,
      expires_at: Math.floor(Date.now() / 1000) + 3600, refresh_token: 'r',
      user: { id: 'u1', email: 'a@example.com', aud: 'authenticated', app_metadata: {}, user_metadata: {} },
    })])
  }
}

test('signed-out users go to the shared /login with next', async ({ page }) => {
  await enableAuth(page, { status: 401, body: {} }, false)
  await page.goto('#posts')
  await page.waitForURL(/\/login\?next=%2Flinkedin$/)
})

test('an expired session (401) goes to /login too', async ({ page }) => {
  await enableAuth(page, { status: 401, body: { detail: 'Authentication required' } })
  await page.goto('#posts')
  await page.waitForURL(/\/login\?next=%2Flinkedin$/)
})

for (const [reason, text] of [['pending', 'waiting for approval'], ['rejected', 'not approved'],
  ['suspended', 'suspended'], ['no_membership', 'does not have access']]) {
  test(`refused (${reason}) shows a message and does not redirect`, async ({ page }) => {
    await enableAuth(page, { status: 403, body: { detail: 'x', reason } })
    await page.goto('#posts')
    await expect(page.getByText(text)).toBeVisible()
    await expect(page.getByRole('link', { name: 'Your account' })).toHaveAttribute('href', '/account')
    await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
    expect(page.url()).toContain('/linkedin/')
  })
}

// Approval revoked / account suspended while the app is open: the next API
// call answers 403 with a reason. That must land on the same refusal screen
// the gate shows, not as scattered error alerts across the workspace.
for (const [reason, text] of [['suspended', 'Your account is suspended.'],
  ['no_membership', 'does not have access']]) {
  test(`a mid-session 403 (${reason}) shows the refusal screen`, async ({ page }) => {
    await enableAuth(page, { status: 200, body: { email: 'a@example.com' } })
    await page.route('**/api/linkedin/posts**', r => r.fulfill({ status: 403, json: {
      detail: 'Access refused', reason } }))
    await page.goto('#posts')
    await expect(page.getByText(text)).toBeVisible()
    await expect(page.getByRole('link', { name: 'Your account' })).toHaveAttribute('href', '/account')
    await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Posts', exact: true })).toHaveCount(0)
    expect(page.url()).toContain('/linkedin/')
  })
}
