import { expect, test } from '@playwright/test'

test('first use opens the Profile tab with the template and saves', async ({ page }) => {
  let saved = ''
  await page.route('**/api/linkedin/profile', async route => {
    if (route.request().method() === 'PUT') {
      saved = route.request().postDataJSON().profile_md
      return route.fulfill({ json: { profile_md: saved, is_set: true, template: 'T', updated_at: null } })
    }
    return route.fulfill({ json: { profile_md: null, is_set: false, template: '# Template', updated_at: null } })
  })
  await page.goto('#posts')
  await expect(page).toHaveURL(/#profile$/)
  await expect(page.getByText('Before your first post')).toBeVisible()
  const editor = page.getByRole('textbox', { name: 'Writer profile' })
  await expect(editor).toHaveValue('# Template')
  await editor.fill('# Asha')
  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect.poll(() => saved).toBe('# Asha')
})

test('a profile over 8000 characters cannot be saved', async ({ page }) => {
  await page.route('**/api/linkedin/profile', r => r.fulfill({ json: {
    profile_md: 'x', is_set: true, template: 'T', updated_at: null } }))
  await page.goto('#profile')
  await page.getByRole('textbox', { name: 'Writer profile' }).fill('x'.repeat(8001))
  await expect(page.getByRole('button', { name: 'Save profile' })).toBeDisabled()
  await expect(page.getByText('8001 / 8000')).toBeVisible()
})

test('creating a post without a profile opens the Profile tab', async ({ page }) => {
  // The profile was set when the page loaded, then is gone (e.g. another tab).
  let refused = false
  await page.route('**/api/linkedin/profile', r => r.fulfill({ json: refused
    ? { profile_md: null, is_set: false, template: '# Template', updated_at: null }
    : { profile_md: 'x', is_set: true, template: 'T', updated_at: null } }))
  await page.route('**/api/linkedin/characters', r => r.fulfill({ json: [
    { character_id: 'asha_bot', display_name: 'Asha Bot', hero_image_url: 'https://h/x.png' }] }))
  await page.route('**/api/linkedin/posts', r => {
    if (r.request().method() !== 'POST') return r.fulfill({ json: [] })
    refused = true
    return r.fulfill({ status: 409, json: { detail: 'Write your writer profile first', reason: 'profile_required' } })
  })
  await page.goto('#posts')
  await page.getByLabel('Your work update').fill('We cut the nightly pipeline from four hours to fifty minutes. '.repeat(3))
  await page.getByRole('button', { name: 'Start this post' }).click()
  await expect(page).toHaveURL(/#profile$/)
  await expect(page.getByText('Before your first post')).toBeVisible()
})
