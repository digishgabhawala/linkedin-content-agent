import { expect, test, type Page } from '@playwright/test'

// Onboarding is Profile -> Mascot -> first post: a post needs a character
// with a locked hero (POST /posts refuses with 409 character_required).

const BRIEF = 'We cut the nightly pipeline from four hours to fifty minutes. '.repeat(3)

function character(id: string, hero: boolean, updatedAt: string) {
  return {
    character_id: id, display_name: id.replace('_', ' '), personality: null, character_card: {},
    hero_asset_id: null, hero_candidate_id: null, hero_version: hero ? 1 : 0,
    hero_image_url: hero ? `https://h/${id}.png` : null, updated_at: updatedAt,
  }
}

async function mockApp(page: Page, characters: unknown[],
  onCreate?: (body: { brief: string; character_id?: string }) => object) {
  await page.route('**/api/linkedin/profile', r => r.fulfill({ json: {
    profile_md: '# Asha', is_set: true, template: 'T', updated_at: null } }))
  await page.route('**/api/linkedin/characters', r => r.fulfill({ json: characters }))
  await page.route('**/api/linkedin/posts', r => {
    if (r.request().method() !== 'POST') return r.fulfill({ json: [] })
    const result = onCreate?.(r.request().postDataJSON())
    return r.fulfill(result ?? { status: 500, json: { detail: 'not mocked' } })
  })
}

test('without a locked-hero character the new-post screen asks for a mascot', async ({ page }) => {
  await mockApp(page, [character('draft_bot', false, '2026-10-16T07:00:00Z')])
  await page.goto('#posts')
  await expect(page.getByRole('heading', { name: 'Create your mascot first' })).toBeVisible()
  await expect(page.getByLabel('Your work update')).toHaveCount(0)
  await page.screenshot({ path: test.info().outputPath('mascot-required.png'), fullPage: true })
  await page.getByRole('link', { name: 'Open Character Studio' }).click()
  await expect(page).toHaveURL(/#characters$/)
})

test('a character_required refusal at create shows the mascot guidance', async ({ page }) => {
  let refused = false
  await page.route('**/api/linkedin/profile', r => r.fulfill({ json: {
    profile_md: '# Asha', is_set: true, template: 'T', updated_at: null } }))
  // The hero was there when the page loaded, then is gone (e.g. another tab).
  await page.route('**/api/linkedin/characters', r => r.fulfill({ json: refused
    ? [] : [character('asha_bot', true, '2026-10-16T07:00:00Z')] }))
  await page.route('**/api/linkedin/posts', r => {
    if (r.request().method() !== 'POST') return r.fulfill({ json: [] })
    refused = true
    return r.fulfill({ status: 409, json: {
      detail: 'Create your mascot first', reason: 'character_required' } })
  })
  let alerted = false
  page.on('dialog', d => { alerted = true; void d.dismiss() })
  await page.goto('#posts')
  await page.getByLabel('Your work update').fill(BRIEF)
  await page.getByRole('button', { name: 'Start this post' }).click()
  await expect(page.getByRole('heading', { name: 'Create your mascot first' })).toBeVisible()
  expect(alerted).toBe(false)
})

test('with one mascot there is no picker and the post uses it', async ({ page }) => {
  let sent: string | undefined = ''
  await mockApp(page, [character('asha_bot', true, '2026-10-16T07:00:00Z'),
    character('draft_bot', false, '2026-10-17T07:00:00Z')], body => {
    sent = body.character_id
    return { status: 409, json: { detail: 'stop here', reason: 'test' } }
  })
  page.on('dialog', d => void d.dismiss())
  await page.goto('#posts')
  await expect(page.getByRole('combobox', { name: 'Mascot' })).toHaveCount(0)
  await page.getByLabel('Your work update').fill(BRIEF)
  await page.getByRole('button', { name: 'Start this post' }).click()
  await expect.poll(() => sent).toBe('asha_bot')
})

test('with several mascots the form offers a picker defaulting to the newest', async ({ page }) => {
  let sent: string | undefined = ''
  await mockApp(page, [character('older_bot', true, '2026-10-10T07:00:00Z'),
    character('newer_bot', true, '2026-10-16T07:00:00Z'),
    character('draft_bot', false, '2026-10-17T07:00:00Z')], body => {
    sent = body.character_id
    return { status: 409, json: { detail: 'stop here', reason: 'test' } }
  })
  page.on('dialog', d => void d.dismiss())
  await page.goto('#posts')
  const picker = page.getByRole('combobox', { name: 'Mascot' })
  await expect(picker.locator('option')).toHaveCount(2) // only characters with a locked hero
  await expect(picker).toHaveValue('newer_bot')
  await picker.selectOption('older_bot')
  await page.getByLabel('Your work update').fill(BRIEF)
  await page.getByRole('button', { name: 'Start this post' }).click()
  await expect.poll(() => sent).toBe('older_bot')
})
