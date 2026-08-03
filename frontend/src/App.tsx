import { useEffect, useState } from 'react'
import { api } from './api'
import { usePostPolling } from './hooks/usePostPolling'
import type { Post } from './types'
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

export default function App() {
  const { post, setPost } = usePostPolling(null)
  const [history, setHistory] = useState<Post[]>([])
  const [busy, setBusy] = useState(false)
  const [imageError, setImageError] = useState<string | null>(null)

  useEffect(() => {
    refreshHistory()
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

  async function run<T>(fn: () => Promise<T>, onError?: (msg: string) => void) {
    setBusy(true)
    try {
      return await fn()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Something went wrong'
      if (onError) onError(msg)
      else alert(msg)
      return undefined
    } finally {
      setBusy(false)
    }
  }

  async function handleNewBrief(brief: string) {
    const p = await run(() => api.createPost(brief))
    if (p) setPost(p)
  }

  async function handleAnswer(answer: string) {
    if (!post) return
    const p = await run(() => api.clarify(post.id, answer))
    if (p) setPost(p)
  }

  async function handleSubmitAdditionalInfo(info: string) {
    if (!post) return
    const p = await run(() => api.submitAdditionalInfo(post.id, info))
    if (p) setPost(p)
  }

  async function handleAcceptDraft() {
    if (!post) return
    const p = await run(() => api.acceptDraft(post.id))
    if (p) setPost(p)
  }

  async function handleRedraft() {
    if (!post) return
    const p = await run(() => api.redraft(post.id))
    if (p) setPost(p)
  }

  async function handleRegenerate(instruction: string) {
    if (!post) return
    const p = await run(() => api.regenerate(post.id, instruction))
    if (p) setPost(p)
  }

  async function handleLock() {
    if (!post) return
    const p = await run(() => api.lock(post.id))
    if (p) setPost(p)
  }

  async function handleUpdateScene(scene: string) {
    if (!post) return
    const p = await run(() => api.updateScene(post.id, scene))
    if (p) setPost(p)
  }

  async function handleForgetAsset(name: string) {
    await run(() => api.deleteSceneAsset(name))
  }

  async function handleGenerateImage() {
    if (!post) return
    setImageError(null)
    const p = await run(
      () => api.generateImage(post.id),
      msg => setImageError(msg)
    )
    if (p) setPost(p)
  }

  async function handleFinalize() {
    if (!post) return
    const p = await run(() => api.finalize(post.id))
    if (p) setPost(p)
  }

  async function handleFeedback(stage: string, note: string) {
    if (!post) return
    await run(() => api.addFeedback(post.id, stage, note))
  }

  function selectFromHistory(p: Post) {
    setImageError(null)
    setPost(p)
  }

  function startNew() {
    setImageError(null)
    setPost(null)
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white px-6 py-4 shadow-sm">
        <h1 className="text-xl font-bold text-gray-900">LinkedIn Content Agent</h1>
        <p className="text-xs text-gray-500 mt-0.5">
          Brief → draft → lock → character render → post
        </p>
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
          {!post && (
            <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
              <BriefForm onSubmit={handleNewBrief} loading={busy} />
            </div>
          )}

          {post && post.status === 'clarifying' && (
            <ClarifyChat post={post} onAnswer={handleAnswer} loading={busy} />
          )}

          {post && post.status === 'needs_input' && (
            <NeedsInput
              post={post}
              onSubmitInfo={handleSubmitAdditionalInfo}
              onAcceptDraft={handleAcceptDraft}
              loading={busy}
            />
          )}

          {post && post.status === 'drafting' && (
            <>
              <DraftPanel
                post={post}
                onRedraft={handleRedraft}
                onRegenerate={handleRegenerate}
                onLock={handleLock}
                loading={busy}
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
                loading={busy}
                error={imageError}
              />
              <FeedbackForm onSubmit={handleFeedback} />
            </>
          )}

          {post && (post.status === 'image_queued' || post.status === 'image_failed') && (
            <ImageStatus post={post} onRetry={handleGenerateImage} />
          )}

          {post && (post.status === 'image_ready' || post.status === 'ready') && (
            <>
              <PostPreview
                post={post}
                onFinalize={handleFinalize}
                onRegenerateImage={handleGenerateImage}
                onUpdateScene={handleUpdateScene}
                onForgetAsset={handleForgetAsset}
                loading={busy}
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
