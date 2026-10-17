import { lazy, Suspense, useEffect, useState } from 'react'
import { api } from './api'
import { usePostPolling } from './hooks/usePostPolling'
import type { Character, ImageReadiness, Post, RendererStatus } from './types'
import { BriefForm } from './components/BriefForm'
import { ClarifyChat } from './components/ClarifyChat'
import { DraftPanel } from './components/DraftPanel'
import { DraftHistory } from './components/DraftHistory'
import { ConversationHistory } from './components/ConversationHistory'
import { PillarScores } from './components/PillarScores'
import { NeedsInput } from './components/NeedsInput'
import { LockAndScene } from './components/LockAndScene'
import { ImageStatus } from './components/ImageStatus'
import { PostPreview } from './components/PostPreview'
import { FeedbackForm } from './components/FeedbackForm'
import { HistorySidebar } from './components/HistorySidebar'
import { ImageMemoryDialog } from './components/ImageMemoryDialog'
import { JourneyProgress } from './components/JourneyProgress'
import { RendererStatusBadge } from './components/RendererStatusBadge'
import { useSession } from './session'
import { ApiError } from './errors'
import { SuiteBrand } from './components/SuiteBrand'
import { StepStatus } from './components/StepStatus'

const CharacterStudio = lazy(() =>
  import('./components/CharacterStudio').then((module) => ({ default: module.CharacterStudio })),
)
const ProfilePage = lazy(() =>
  import('./components/ProfilePage').then((module) => ({ default: module.ProfilePage })),
)
const BackdropsPage = lazy(() =>
  import('./components/BackdropsPage').then((module) => ({ default: module.BackdropsPage })),
)

type AppView = 'posts' | 'characters' | 'backdrops' | 'profile'

function viewFromHash(): AppView {
  if (window.location.hash.startsWith('#characters')) return 'characters'
  if (window.location.hash.startsWith('#backdrops')) return 'backdrops'
  if (window.location.hash.startsWith('#profile')) return 'profile'
  return 'posts'
}

function postIdFromHash() {
  if (!window.location.hash.startsWith('#posts?')) return null
  return new URLSearchParams(window.location.hash.split('?', 2)[1]).get('post')
}

export default function App() {
  const session = useSession()
  const [activeView, setActiveView] = useState<AppView>(viewFromHash)
  const [characterStudioDirty, setCharacterStudioDirty] = useState(false)
  const { post, setPost } = usePostPolling(null)
  const [history, setHistory] = useState<Post[]>([])
  const [busy, setBusy] = useState(false)
  const [imageError, setImageError] = useState<string | null>(null)
  const [imageReadiness, setImageReadiness] = useState<ImageReadiness | null>(null)
  const [showMemoryDialog, setShowMemoryDialog] = useState(false)
  const [journeyActivity, setJourneyActivity] = useState<string | null>(null)
  const [rendererStatus, setRendererStatus] = useState<RendererStatus | null>(null)
  const [onboarding, setOnboarding] = useState(false)
  const [characters, setCharacters] = useState<Character[]>([])
  const [characterRequired, setCharacterRequired] = useState(false)
  const needsCharacter = !!post && post.status === 'locked'
    && (post.character_id === null || characterRequired)

  // The image card offers the owner's characters only when the post needs one.
  useEffect(() => {
    if (!needsCharacter) return
    let active = true
    api.listCharacters().then(list => { if (active) setCharacters(list) }).catch(() => {})
    return () => { active = false }
  }, [needsCharacter])

  useEffect(() => {
    setCharacterRequired(false)
  }, [post?.id])

  useEffect(() => {
    refreshHistory()
  }, [])

  // First use: no writer profile yet -> open the Profile tab with the template.
  function openOnboarding() {
    setOnboarding(true)
    window.location.hash = '#profile'
  }

  useEffect(() => {
    let active = true
    api.getProfile()
      .then(profile => { if (active && !profile.is_set) openOnboarding() })
      .catch(() => {})
    return () => { active = false }
  }, [])

  useEffect(() => {
    const syncView = () => {
      setActiveView(viewFromHash())
      const requestedPostId = postIdFromHash()
      if (requestedPostId) {
        void api.getPost(requestedPostId).then(setPost).catch(() => {})
      }
    }
    syncView()
    window.addEventListener('hashchange', syncView)
    return () => window.removeEventListener('hashchange', syncView)
  }, [setPost])

  useEffect(() => {
    let active = true
    async function refreshRendererStatus() {
      try {
        const status = await api.rendererStatus()
        if (active) setRendererStatus(status)
      } catch {
        if (active) {
          setRendererStatus({
            reachable: false,
            online: false,
            online_count: 0,
            busy_count: 0,
            last_seen_at: null,
            message: 'Could not reach this app’s backend',
            workers: [],
          })
        }
      }
    }
    void refreshRendererStatus()
    // Heartbeats arrive every 60s, so polling faster than ~15s shows nothing new.
    const interval = window.setInterval(refreshRendererStatus, 15000)
    return () => {
      active = false
      clearInterval(interval)
    }
  }, [])

  // keep the sidebar's status labels in sync once the active post changes
  useEffect(() => {
    if (post?.status) refreshHistory()
  }, [post?.status])

  async function refreshHistory() {
    try {
      setHistory(await api.listPosts())
    } catch {
      /* ignore */
    }
  }

  async function run<T>(
    fn: () => Promise<T>,
    onError?: (msg: string) => void,
    activity?: string,
  ) {
    setBusy(true)
    setJourneyActivity(activity ?? null)
    try {
      return await fn()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Something went wrong'
      if (onError) onError(msg)
      else alert(msg)
      return undefined
    } finally {
      setBusy(false)
      setJourneyActivity(null)
    }
  }

  // A request in flight OR a queue step still running: actions stay disabled.
  const working = busy || !!post?.active_step

  async function handleRetryStep() {
    if (!post) return
    const p = await run(() => api.retryStep(post.id), undefined, 'Submitting…')
    if (p) setPost(p)
  }

  async function handleNewBrief(brief: string) {
    const p = await run(async () => {
      try {
        return await api.createPost(brief)
      } catch (e) {
        if (e instanceof ApiError && e.reason === 'profile_required') {
          openOnboarding()
          return undefined
        }
        throw e
      }
    }, undefined, 'Submitting…')
    if (p) setPost(p)
  }

  async function handleAnswer(answer: string) {
    if (!post) return
    const p = await run(() => api.clarify(post.id, answer), undefined, 'Submitting…')
    if (p) setPost(p)
  }

  async function handleSubmitAdditionalInfo(info: string) {
    if (!post) return
    const p = await run(
      () => api.submitAdditionalInfo(post.id, info),
      undefined,
      'Submitting…',
    )
    if (p) setPost(p)
  }

  async function handleAcceptDraft() {
    if (!post) return
    const p = await run(() => api.acceptDraft(post.id), undefined, 'Accepting this draft…')
    if (p) setPost(p)
  }

  async function handleRedraft() {
    if (!post) return
    const p = await run(() => api.redraft(post.id), undefined, 'Submitting…')
    if (p) setPost(p)
  }

  async function handleRegenerate(instruction: string) {
    if (!post) return
    const p = await run(
      () => api.regenerate(post.id, instruction),
      undefined,
      'Submitting…',
    )
    if (p) setPost(p)
  }

  async function handleLock() {
    if (!post) return
    const p = await run(() => api.lock(post.id), undefined, 'Submitting…')
    if (p) setPost(p)
  }

  async function handleUpdateScene(scene: string) {
    if (!post) return
    const p = await run(() => api.updateScene(post.id, scene), undefined, 'Saving the image scene…')
    if (p) setPost(p)
  }

  async function handleUseLatestBackdrop() {
    if (!post) return
    const p = await run(
      () => api.useLatestBackdrop(post.id),
      undefined,
      'Updating the backdrop version…',
    )
    if (p) setPost(p)
  }

  async function handleBackdropChange(name: string | null) {
    if (!post) return
    const updated = await run(
      () => api.updatePostBackdrop(post.id, name),
      undefined,
      'Updating the recurring backdrop…',
    )
    if (updated) setPost(updated)
  }

  /** 409 character_required: show the character choice instead of an alert. */
  function characterRequiredShown(e: unknown): boolean {
    // Only the locked post's image card has the choice; elsewhere the alert stays.
    if (e instanceof ApiError && e.reason === 'character_required' && post?.status === 'locked') {
      setCharacterRequired(true)
      return true
    }
    return false
  }

  async function handleSetCharacter(characterId: string) {
    if (!post) return
    const p = await run(() => api.setPostCharacter(post.id, characterId), undefined,
      'Choosing the character…')
    if (p) {
      setCharacterRequired(false)
      setPost(p)
    }
  }

  async function handleGenerateImage() {
    if (!post) return
    setImageError(null)
    setBusy(true)
    setJourneyActivity('Checking render memory…')
    try {
      const readiness = await api.imageReadiness()
      setImageReadiness(readiness)
      if (readiness.enough_memory) {
        setJourneyActivity('Submitting the image task…')
        const p = await api.generateImage(post.id, 'full')
        setPost(p)
      } else {
        setShowMemoryDialog(true)
      }
    } catch (e: unknown) {
      if (characterRequiredShown(e)) return
      const msg = e instanceof Error ? e.message : 'Could not check image-render memory'
      setImageError(msg)
      alert(msg)
    } finally {
      setBusy(false)
      setJourneyActivity(null)
    }
  }

  async function handleMemoryRescan() {
    if (!post) return
    setBusy(true)
    setJourneyActivity('Rescanning available memory…')
    try {
      const readiness = await api.imageReadiness()
      setImageReadiness(readiness)
      if (readiness.enough_memory) {
        setShowMemoryDialog(false)
        setJourneyActivity('Submitting the image task…')
        const p = await api.generateImage(post.id, 'full')
        setPost(p)
      }
    } catch (e: unknown) {
      if (characterRequiredShown(e)) {
        setShowMemoryDialog(false)
        return
      }
      alert(e instanceof Error ? e.message : 'Could not rescan memory')
    } finally {
      setBusy(false)
      setJourneyActivity(null)
    }
  }

  async function handleMemoryChoice(profile: 'full' | 'lightning') {
    if (!post) return
    setBusy(true)
    setJourneyActivity(
      profile === 'lightning' ? 'Submitting a Lightning render…' : 'Submitting a full-quality render…',
    )
    try {
      const p = await api.generateImage(post.id, profile)
      setShowMemoryDialog(false)
      setPost(p)
    } catch (e: unknown) {
      if (characterRequiredShown(e)) {
        setShowMemoryDialog(false)
        return
      }
      alert(e instanceof Error ? e.message : 'Could not start image generation')
    } finally {
      setBusy(false)
      setJourneyActivity(null)
    }
  }

  async function handleFinalize() {
    if (!post) return
    const p = await run(() => api.finalize(post.id), undefined, 'Marking the post ready…')
    if (p) setPost(p)
  }

  async function handleFeedback(stage: string, note: string) {
    if (!post) return
    await run(() => api.addFeedback(post.id, stage, note))
  }

  function selectFromHistory(p: Post) {
    setImageError(null)
    setShowMemoryDialog(false)
    setPost(p)
  }

  function startNew() {
    setImageError(null)
    setShowMemoryDialog(false)
    setPost(null)
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <a className="app-skip-link" href={
        activeView === 'characters'
          ? '#characters-main-content'
          : activeView === 'backdrops' ? '#backdrops-main-content'
            : activeView === 'profile' ? '#profile-main-content' : '#posts-main-content'
      }>
        Skip to main content
      </a>
      {showMemoryDialog && imageReadiness && (
        <ImageMemoryDialog
          readiness={imageReadiness}
          loading={working}
          onRescan={handleMemoryRescan}
          onFullQuality={() => handleMemoryChoice('full')}
          onLightning={() => handleMemoryChoice('lightning')}
          onCancel={() => setShowMemoryDialog(false)}
        />
      )}
      <header className="border-b border-gray-200 bg-white px-5 py-4 shadow-sm sm:px-6">
        <div className="mx-auto flex max-w-5xl flex-col items-start justify-between gap-4 md:flex-row md:items-center md:gap-6">
          <div>
            <SuiteBrand />
            <h1 className="mt-2 text-xl font-bold text-gray-900">LinkedIn Content Agent</h1>
            <p className="text-xs text-gray-500 mt-0.5">
              Brief → draft → lock → character render → post
            </p>
          </div>
          <div className="flex w-full flex-wrap items-center gap-4 md:w-auto md:justify-end">
            <RendererStatusBadge status={rendererStatus} />
            {session.email && (
              <div className="flex items-center gap-2 text-xs text-gray-600">
                <span>{session.email}</span>
                <a href="/account" className="min-h-11 rounded-lg border border-gray-300 px-3 py-2 hover:bg-gray-50">
                  Account
                </a>
                <button onClick={session.signOut} className="min-h-11 rounded-lg border border-gray-300 px-3 py-2 hover:bg-gray-50">
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <nav className="app-primary-nav" aria-label="LinkedIn Content Agent">
        <div className="app-primary-nav__inner">
          <a
            href="#posts"
            aria-current={activeView === 'posts' ? 'page' : undefined}
            onClick={(event) => {
              if (characterStudioDirty && activeView === 'characters'
                && !window.confirm('Discard this unfinished character card?')) {
                event.preventDefault()
              }
            }}
          >
            Posts
          </a>
          <a
            href="#characters"
            aria-current={activeView === 'characters' ? 'page' : undefined}
          >
            Character Studio
          </a>
          <a
            href="#backdrops"
            aria-current={activeView === 'backdrops' ? 'page' : undefined}
            onClick={(event) => {
              if (characterStudioDirty && activeView === 'characters'
                && !window.confirm('Discard this unfinished character card?')) {
                event.preventDefault()
              }
            }}
          >
            Backdrops
          </a>
          <a
            href="#profile"
            aria-current={activeView === 'profile' ? 'page' : undefined}
            onClick={(event) => {
              if (characterStudioDirty && activeView === 'characters'
                && !window.confirm('Discard this unfinished character card?')) {
                event.preventDefault()
              }
            }}
          >
            Profile
          </a>
        </div>
      </nav>

      {activeView === 'characters' ? (
        <Suspense fallback={(
          <main id="characters-main-content" className="mx-auto max-w-5xl px-6 py-10">
            <p role="status" className="text-sm text-gray-600">Loading Character Studio…</p>
          </main>
        )}>
          <CharacterStudio onDirtyChange={setCharacterStudioDirty} />
        </Suspense>
      ) : activeView === 'profile' ? (
        <Suspense fallback={(
          <main id="profile-main-content" className="mx-auto max-w-5xl px-6 py-10">
            <p role="status" className="text-sm text-gray-600">Loading Profile…</p>
          </main>
        )}>
          <ProfilePage onboarding={onboarding} onSaved={() => setOnboarding(false)} />
        </Suspense>
      ) : activeView === 'backdrops' ? (
        <Suspense fallback={(
          <main id="backdrops-main-content" className="mx-auto max-w-5xl px-6 py-10">
            <p role="status" className="text-sm text-gray-600">Loading Backdrops…</p>
          </main>
        )}>
          <BackdropsPage />
        </Suspense>
      ) : <main id="posts-main-content" className="posts-page">
        <header className="posts-hero">
          <div>
            <p className="posts-eyebrow">Content workspace</p>
            <h2>Posts</h2>
            <p>
              Shape a real work update into a quality-checked LinkedIn post and a
              consistent character illustration.
            </p>
          </div>
          {post && (
            <button type="button" className="post-button post-button--primary posts-new-button" onClick={startNew}>
              Create new post
            </button>
          )}
        </header>

        <div className={`posts-layout ${history.length === 0 ? 'posts-layout--single' : ''}`}>
          {history.length > 0 && (
            <HistorySidebar
              history={history}
              activeId={post?.id ?? null}
              onSelect={selectFromHistory}
            />
          )}

          <div className="posts-workspace">
          {post && <JourneyProgress post={post} activity={journeyActivity} />}

          {post && <StepStatus post={post} onRetry={handleRetryStep} loading={working} />}

          {!post && (
            <section className="post-panel post-panel--brief" aria-labelledby="new-post-heading">
              <BriefForm onSubmit={handleNewBrief} loading={working} />
            </section>
          )}

          {post && post.status === 'clarifying' && (
            <ClarifyChat post={post} onAnswer={handleAnswer} loading={working} />
          )}

          {post && post.status === 'needs_input' && (
            <NeedsInput
              post={post}
              onSubmitInfo={handleSubmitAdditionalInfo}
              onAcceptDraft={handleAcceptDraft}
              loading={working}
            />
          )}

          {post && post.status === 'drafting' && (
            <>
              <DraftPanel
                post={post}
                onRedraft={handleRedraft}
                onRegenerate={handleRegenerate}
                onLock={handleLock}
                loading={working}
              />
              <FeedbackForm onSubmit={handleFeedback} />
            </>
          )}

          {post && post.status === 'locked' && (
            <>
              <LockAndScene
                post={post}
                characters={characters}
                characterRequired={characterRequired}
                onSetCharacter={handleSetCharacter}
                onUpdateScene={handleUpdateScene}
                onBackdropChange={handleBackdropChange}
                onUseLatestBackdrop={handleUseLatestBackdrop}
                onGenerateImage={handleGenerateImage}
                loading={working}
                error={imageError}
              />
              <FeedbackForm onSubmit={handleFeedback} />
            </>
          )}

          {post && (post.status === 'image_queued' || post.status === 'image_failed') && (
            <ImageStatus
              post={post}
              // Retry repeats the profile the user last chose (a failed
              // Lightning render must not silently come back as Full).
              onRetry={() => handleMemoryChoice(post.image_profile ?? 'full')}
              onRetryLightning={() => handleMemoryChoice('lightning')}
            />
          )}

          {post && (post.status === 'image_ready' || post.status === 'ready') && (
            <>
              <PostPreview
                post={post}
                onFinalize={handleFinalize}
                onRegenerateImage={handleGenerateImage}
                onUpdateScene={handleUpdateScene}
                onBackdropChange={handleBackdropChange}
                onUseLatestBackdrop={handleUseLatestBackdrop}
                loading={working}
              />
              <FeedbackForm onSubmit={handleFeedback} />
            </>
          )}

          {post && post.status !== 'clarifying' && post.status !== 'needs_input' && (
            <PillarScores post={post} />
          )}

          {post && post.status !== 'clarifying' && (
            <>
              <ConversationHistory post={post} />
              <DraftHistory postId={post.id} currentVersion={post.draft_version} />
            </>
          )}
          </div>
        </div>
      </main>}
    </div>
  )
}
