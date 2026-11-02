import { expect, test, type Page } from '@playwright/test'

const TEMPLATES = [
  {
    id: 'junior_engineer',
    label: 'Junior engineer',
    description: 'Early career, learning in public',
    profile_md: '# Writer profile\n\nI have [years of experience] in software.',
  },
  {
    id: 'senior_engineer',
    label: 'Senior engineer',
    description: 'Shipping and debugging real systems',
    profile_md: '# Writer profile\n\nI build [what you build].',
  },
  {
    id: 'engineering_manager',
    label: 'Engineering manager',
    description: 'Teams, delivery, hiring',
    profile_md: '# Writer profile\n\nI manage [kind of team].',
  },
  {
    id: 'product_lead',
    label: 'Product lead',
    description: 'Users, trade-offs, decisions',
    profile_md: '# Writer profile\n\nI lead [kind of product].',
  },
  {
    id: 'platform_lead_architect',
    label: 'Platform lead / architect',
    description: 'Systems, standards, build-vs-buy',
    profile_md: '# Writer profile\n\nI lead [platform area].',
  },
]

async function mockProfile(page: Page, profile: {
  profile_md: string | null
  is_set: boolean
}) {
  await page.route('**/api/linkedin/profile', route => route.fulfill({ json: {
    ...profile,
    templates: TEMPLATES,
    updated_at: null,
  } }))
}

test('first use shows the template picker and an empty editor', async ({ page }) => {
  await mockProfile(page, { profile_md: null, is_set: false })
  await page.goto('#posts')

  await expect(page).toHaveURL(/#profile$/)
  await expect(page.getByText('Before your first post')).toBeVisible()
  const picker = page.getByRole('combobox', { name: 'Start from a template' })
  await expect(picker).toHaveValue('')
  await expect(picker.locator('option')).toHaveCount(7)
  await expect(page.getByRole('textbox', { name: 'Writer profile' })).toHaveValue('')
  await expect(page.getByText('Pick a template to start from, or write your own.')).toBeVisible()
})

test('choosing a template fills the editor and shows the placeholder warning', async ({ page }) => {
  await mockProfile(page, { profile_md: null, is_set: false })
  await page.goto('#profile')

  await page.getByRole('combobox', { name: 'Start from a template' })
    .selectOption('junior_engineer')
  await expect(page.getByRole('textbox', { name: 'Writer profile' }))
    .toHaveValue(TEMPLATES[0].profile_md)
  await expect(page.getByText(
    'This is a generic profile. Replace the [bracketed] parts with your own details so your posts sound like you.',
  )).toBeVisible()
})

test('switching template after typing asks for confirmation', async ({ page }) => {
  await mockProfile(page, { profile_md: null, is_set: false })
  await page.goto('#profile')
  const editor = page.getByRole('textbox', { name: 'Writer profile' })
  const picker = page.getByRole('combobox', { name: 'Start from a template' })
  await editor.fill('My hand-written profile')

  let asked = false
  page.once('dialog', async dialog => {
    asked = true
    expect(dialog.message()).toContain('Replace the profile text')
    await dialog.dismiss()
  })
  await picker.selectOption('senior_engineer')

  expect(asked).toBe(true)
  await expect(editor).toHaveValue('My hand-written profile')
})

test('saved profile hides the picker and shows the disabled coming-soon button', async ({ page }) => {
  await mockProfile(page, { profile_md: '# Writer', is_set: true })
  await page.goto('#profile')

  await expect(page.getByRole('combobox', { name: 'Start from a template' })).toHaveCount(0)
  await expect(page.getByRole('button', {
    name: 'Update profile from template · Coming soon',
  })).toBeDisabled()
  await page.getByRole('textbox', { name: 'Writer profile' }).fill('# Writer\n\nUpdated role')
  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect(page).toHaveURL(/#profile$/)
  await expect(page.getByText('Profile saved.')).toBeVisible()
})

test('warning disappears once no [bracketed] parts remain', async ({ page }) => {
  await mockProfile(page, { profile_md: null, is_set: false })
  await page.goto('#profile')
  await page.getByRole('combobox', { name: 'Start from a template' })
    .selectOption('junior_engineer')
  const warning = page.getByText('This is a generic profile.', { exact: false })
  await expect(warning).toBeVisible()

  await page.getByRole('textbox', { name: 'Writer profile' })
    .fill('# Writer profile\n\nI lead a cross-functional product team.')
  await expect(warning).toHaveCount(0)
})

test('first profile save continues to Character Studio', async ({ page }) => {
  await page.route('**/api/linkedin/profile', route => {
    if (route.request().method() === 'PUT') {
      expect(route.request().postDataJSON()).toEqual({
        profile_md: '# Writer profile\n\nI lead a cross-functional product team.',
      })
      return route.fulfill({ json: {
        profile_md: '# Writer profile\n\nI lead a cross-functional product team.',
        is_set: true,
        templates: TEMPLATES,
        updated_at: '2026-11-02T08:00:00Z',
      } })
    }
    return route.fulfill({ json: {
      profile_md: null,
      is_set: false,
      templates: TEMPLATES,
      updated_at: null,
    } })
  })
  await page.route('**/api/linkedin/characters', route => route.fulfill({ json: [] }))
  await page.goto('#profile')

  await page.getByRole('textbox', { name: 'Writer profile' })
    .fill('# Writer profile\n\nI lead a cross-functional product team.')
  await page.getByRole('button', { name: 'Save profile' }).click()

  await expect(page).toHaveURL(/#characters$/)
  await expect(page.getByRole('heading', { name: 'Character Studio' })).toBeVisible()
})

test('a profile over 8000 characters cannot be saved', async ({ page }) => {
  await mockProfile(page, { profile_md: 'x', is_set: true })
  await page.goto('#profile')
  await page.getByRole('textbox', { name: 'Writer profile' }).fill('x'.repeat(8001))
  await expect(page.getByRole('button', { name: 'Save profile' })).toBeDisabled()
  await expect(page.getByText('8001 / 8000')).toBeVisible()
})

test('creating a post without a profile opens the Profile tab', async ({ page }) => {
  // The profile was set when the page loaded, then is gone (e.g. another tab).
  let refused = false
  await page.route('**/api/linkedin/profile', route => route.fulfill({ json: {
    profile_md: refused ? null : 'x',
    is_set: !refused,
    templates: TEMPLATES,
    updated_at: null,
  } }))
  await page.route('**/api/linkedin/characters', route => route.fulfill({ json: [
    { character_id: 'asha_bot', display_name: 'Asha Bot', hero_image_url: 'https://h/x.png' },
  ] }))
  await page.route('**/api/linkedin/posts', route => {
    if (route.request().method() !== 'POST') return route.fulfill({ json: [] })
    refused = true
    return route.fulfill({ status: 409, json: {
      detail: 'Write your writer profile first', reason: 'profile_required',
    } })
  })
  await page.goto('#posts')
  await page.getByLabel('Your work update')
    .fill('We cut the nightly pipeline from four hours to fifty minutes. '.repeat(3))
  await page.getByRole('button', { name: 'Start this post' }).click()
  await expect(page).toHaveURL(/#profile$/)
  await expect(page.getByText('Before your first post')).toBeVisible()
})
