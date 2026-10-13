import { useEffect, useState } from 'react'
import { api } from './api'
import { usePostPolling } from './hooks/usePostPolling'
import type { ImageReadiness, Post, RendererStatus } from './types'
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
import { SceneAssetsPanel } from './components/SceneAssetsPanel'
import { ImageMemoryDialog } from './components/ImageMemoryDialog'
import { JourneyProgress } from './components/JourneyProgress'
import { RendererStatusBadge } from './components/RendererStatusBadge'
import { useSession } from './session'
import { StepStatus } from './components/StepStatus'

export default function App() {
  const session = useSession()
  const { post, setPost } = usePostPolling(null)
  const [history, setHistory] = useState<Post[]>([])
  const [busy, setBusy] = useState(false)
  const [imageError, setImageError] = useState<string | null>(null)
  const [imageReadiness, setImageReadiness] = useState<ImageReadiness | null>(null)
  const [showMemoryDialog, setShowMemoryDialog] = useState(false)
  const [journeyActivity, setJourneyActivity] = useState<string | null>(null)
  const [rendererStatus, setRendererStatus] = useState<RendererStatus | null>(null)

  useEffect(() => {
    refreshHistory()
  }, [])

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
    const p = await run(() => api.createPost(brief), undefined, 'Submitting…')
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

  async function handleForgetAsset(name: string) {
    await run(() => api.deleteSceneAsset(name))
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
      <header className="border-b border-gray-200 bg-white px-6 py-4 shadow-sm">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-6">
          <div>
            <h1 className="text-xl font-bold text-gray-900">LinkedIn Content Agent</h1>
            <p className="text-xs text-gray-500 mt-0.5">
              Brief → draft → lock → character render → post
            </p>
          </div>
          <div className="flex items-center gap-4">
            <RendererStatusBadge status={rendererStatus} />
            {session.email && (
              <div className="flex items-center gap-2 text-xs text-gray-600">
                <span>{session.email}</span>
                <button onClick={session.signOut} className="rounded-lg border border-gray-300 px-2 py-1 hover:bg-gray-50">
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-6 py-8 flex gap-6">
        {history.length > 0 && (
          <div className="w-64 shrink-0 space-y-4">
            <HistorySidebar
              history={history}
              activeId={post?.id ?? null}
              onSelect={selectFromHistory}
              onNew={startNew}
            />
            <SceneAssetsPanel />
          </div>
        )}

        <main className="flex-1 space-y-6">
          {post && <JourneyProgress post={post} activity={journeyActivity} />}

          {post && <StepStatus post={post} onRetry={handleRetryStep} loading={working} />}

          {!post && (
            <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
              <BriefForm onSubmit={handleNewBrief} loading={working} />
            </div>
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
                onUpdateScene={handleUpdateScene}
                onGenerateImage={handleGenerateImage}
                onForgetAsset={handleForgetAsset}
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
                onForgetAsset={handleForgetAsset}
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
        </main>
      </div>
    </div>
  )
}
