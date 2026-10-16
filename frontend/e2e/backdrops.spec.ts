import { expect, test } from '@playwright/test'

test.describe.serial('Backdrops library', () => {
  test('supports the complete backdrop lifecycle on desktop', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'desktop-chromium', 'Desktop lifecycle coverage')
    await page.goto('#backdrops')

    await expect(page.getByRole('link', { name: 'Backdrops' })).toHaveAttribute('aria-current', 'page')
    await expect(page.getByRole('heading', { name: 'Backdrops', exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'No active backdrops yet' })).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath('backdrops-empty-desktop.png'), fullPage: true })

    await page.getByRole('button', { name: 'Create backdrop' }).click()
    await page.getByLabel('Display name (required)').fill('Playwright Studio')
    await page.getByLabel('Backdrop description (required)').fill(
      'A calm editorial studio with a walnut desk, soft window light, and an abstract planning board.',
    )
    await expect(page.getByText('Stable ID:')).toContainText('@playwright_studio')
    await page.getByRole('button', { name: 'Create backdrop', exact: true }).click()

    const card = page.getByRole('article').filter({ hasText: 'Playwright Studio' })
    await expect(card).toContainText('@playwright_studio')
    await expect(card).toContainText('Version 1')
    await expect(card).toContainText('0 posts')
    await page.screenshot({ path: testInfo.outputPath('backdrops-active-desktop.png'), fullPage: true })

    await card.getByRole('button', { name: 'Edit' }).click()
    await card.getByLabel('Display name').fill('Editorial Studio')
    await card.getByLabel('Description').fill(
      'A calm editorial studio with a walnut desk, warm side lighting, and an abstract planning board.',
    )
    await card.getByRole('button', { name: 'Save changes' }).click()

    const updatedCard = page.getByRole('article').filter({ hasText: 'Editorial Studio' })
    await expect(updatedCard).toContainText('@playwright_studio')
    await expect(updatedCard).toContainText('Version 2')
    await updatedCard.getByRole('button', { name: 'Version history' }).click()
    const history = updatedCard.getByRole('list', { name: 'Editorial Studio version history' })
    await expect(history.getByText('Version 1', { exact: true })).toBeVisible()
    await expect(history.getByText('Version 2', { exact: true })).toBeVisible()
    await expect(history.getByText('Used by 0 posts')).toHaveCount(2)
    await page.screenshot({ path: testInfo.outputPath('backdrops-history-desktop.png'), fullPage: true })

    page.once('dialog', dialog => dialog.accept())
    await updatedCard.getByRole('button', { name: 'Archive' }).click()
    const archivedSection = page.getByRole('region', { name: 'Archived' })
    await expect(archivedSection).toContainText('Editorial Studio')
    await expect(archivedSection).toContainText('Archived')
    await page.screenshot({ path: testInfo.outputPath('backdrops-archived-desktop.png'), fullPage: true })
    await archivedSection.getByRole('button', { name: 'Restore backdrop' }).click()
    await expect(page.getByRole('region', { name: 'Archived' })).toHaveCount(0)
    await expect(page.getByRole('article').filter({ hasText: 'Editorial Studio' })).toBeVisible()
  })

  test('fits the backdrop library at a mobile viewport', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'mobile-chromium', 'Mobile layout coverage')
    await page.goto('#backdrops')
    await expect(page.getByRole('heading', { name: 'Backdrops', exact: true })).toBeVisible()

    const viewportMetrics = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))
    expect(viewportMetrics.scrollWidth).toBeLessThanOrEqual(viewportMetrics.clientWidth)
    await page.screenshot({ path: testInfo.outputPath('backdrops-mobile.png'), fullPage: true })
  })
})
