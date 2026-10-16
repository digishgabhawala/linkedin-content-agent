import { expect, test, type Page } from '@playwright/test'
import type { Post, PostDraft } from '../src/types'

const demoPost: Post = {
  id: 'post-demo',
  character_id: 'gtee_dev',
  brief: 'Reduced image-pipeline memory use without slowing down renders.',
  status: 'drafting',
  pending_question: null,
  clarify_transcript: [
    {
      question: 'What changed technically?',
      answer: 'We unload the text model before ComfyUI starts and reuse the same worker queue.',
    },
  ],
  post_text: `The fix was not a bigger machine. It was better sequencing.

Our image pipeline occasionally ran out of memory because the text model and ComfyUI overlapped. We now unload the text model before rendering begins, while keeping both workloads on the same durable queue.

The result: lower peak memory, no measurable slowdown, and a workflow that is easier to recover when a worker disappears.

Resource constraints often reveal architecture problems before scale does.`,
  draft_version: 2,
  category: 'technical_deep_dive',
  gate_scores: {
    factual_integrity: { score: 9.5, reason: 'All claims are grounded in the supplied brief.' },
    voice_authenticity: { score: 9.1, reason: 'Direct and specific without sounding promotional.' },
  },
  pillar_scores: {
    hook: { score: 8.4, reason: 'Opens with a useful contrast.' },
    structure: { score: 8.8, reason: 'Problem, intervention, and result are easy to follow.' },
    topic_resonance: { score: 8.2, reason: 'Useful to engineers operating local AI workloads.' },
  },
  weighted_score: 8.8,
  recalibration_count: 2,
  escalation_reason: null,
  scene_instruction: null,
  scene_asset_name: null,
  scene_asset_display_name: null,
  scene_asset_version: null,
  scene_asset_latest_version: null,
  scene_asset_is_latest: true,
  seed: null,
  image_url: null,
  has_final_image: false,
  image_job_error: null,
  image_queue_status: null,
  image_claimed_at: null,
  is_queue_delayed: false,
  is_stalled: false,
  image_worker_id: null,
  image_progress_stage: null,
  image_progress_message: null,
  image_progress_updated_at: null,
  is_worker_lost: false,
  active_step: null,
  step_error: null,
  can_retry_step: false,
  image_failure_kind: null,
  image_profile: null,
  image_started_at: null,
  created_at: '2026-10-15T09:00:00Z',
  updated_at: '2026-10-16T07:00:00Z',
}

const demoDrafts: PostDraft[] = [
  {
    id: 'draft-1',
    version: 1,
    post_text: 'An earlier version of the post.',
    generated_by: 'initial',
    user_instruction: null,
    created_at: '2026-10-16T06:55:00Z',
  },
  {
    id: 'draft-2',
    version: 2,
    post_text: demoPost.post_text ?? '',
    generated_by: 'regenerate',
    user_instruction: 'Make the technical trade-off clearer.',
    created_at: '2026-10-16T07:00:00Z',
  },
]

async function mockPosts(page: Page, posts: Post[]) {
  await page.route('**/api/linkedin/posts**', async route => {
    const pathname = new URL(route.request().url()).pathname
    if (pathname.endsWith('/posts')) {
      await route.fulfill({ json: posts })
      return
    }
    if (pathname.endsWith('/posts/post-demo/drafts')) {
      await route.fulfill({ json: demoDrafts })
      return
    }
    if (pathname.endsWith('/posts/post-demo')) {
      await route.fulfill({ json: demoPost })
      return
    }
    await route.fallback()
  })
}

test.describe('Posts workspace', () => {
  test('presents a focused empty state on desktop', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'desktop-chromium', 'Desktop empty-state coverage')
    await mockPosts(page, [])
    await page.goto('#posts')

    await expect(page.getByRole('heading', { name: 'Posts', exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'What did you work on?' })).toBeVisible()
    await expect(page.getByLabel('Your work update')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Start this post' })).toBeDisabled()
    await page.screenshot({ path: testInfo.outputPath('posts-empty-desktop.png'), fullPage: true })

    await page.keyboard.press('Tab')
    await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeVisible()
  })

  test('keeps an active draft readable and responsive', async ({ page }, testInfo) => {
    await mockPosts(page, [demoPost])
    await page.goto('#posts')
    await page.getByRole('button', { name: /Reduced image-pipeline memory use/ }).click()

    await expect(page.getByText('Step 2 of 5: Draft & improve')).toBeVisible()
    await expect(page.getByText('Draft v2')).toBeVisible()
    await expect(page.getByLabel('How should this draft change?')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Lock this draft' })).toBeVisible()

    const viewportMetrics = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))
    expect(viewportMetrics.scrollWidth).toBeLessThanOrEqual(viewportMetrics.clientWidth)
    await expect(page.locator('.app-skip-link')).not.toBeFocused()
    await expect(page.locator('.app-skip-link')).toHaveCSS('opacity', '0')

    const suffix = testInfo.project.name === 'mobile-chromium' ? 'mobile' : 'desktop'
    await page.screenshot({ path: testInfo.outputPath(`posts-active-${suffix}.png`), fullPage: true })
  })
})
