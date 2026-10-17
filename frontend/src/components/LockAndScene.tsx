import { useEffect, useState } from 'react'
import type { Character, Post } from '../types'
import { BackdropSelector } from './BackdropSelector'

interface Props {
  post: Post
  characters: Character[]
  // The server refused the image for want of a character (409 character_required).
  characterRequired: boolean
  onSetCharacter: (characterId: string) => void
  onUpdateScene: (scene: string) => void
  onBackdropChange: (name: string | null) => void
  onUseLatestBackdrop: () => void
  onGenerateImage: () => void
  loading: boolean
  error: string | null
}

function CharacterChoice({ characters, loading, onSetCharacter }: {
  characters: Character[]
  loading: boolean
  onSetCharacter: (characterId: string) => void
}) {
  const withHero = characters.filter(c => c.hero_image_url)
  const [choice, setChoice] = useState('')
  const selected = withHero.some(c => c.character_id === choice) ? choice : withHero[0]?.character_id ?? ''

  return (
    <div className="post-field" role="group" aria-labelledby="character-choice-heading">
      <p id="character-choice-heading" className="post-message post-message--warning">
        Choose a character for this image
      </p>
      {withHero.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="Character" value={selected} onChange={e => setChoice(e.target.value)}
            disabled={loading} className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
            {withHero.map(c => (
              <option key={c.character_id} value={c.character_id}>
                {c.display_name || c.character_id}
              </option>
            ))}
          </select>
          <button type="button" disabled={loading || !selected}
            onClick={() => onSetCharacter(selected)}
            className="post-button post-button--secondary">
            Use this character
          </button>
        </div>
      ) : (
        <p className="text-sm text-gray-700">
          You don't have a character with a locked hero yet.{' '}
          <a href="#characters" className="font-medium text-blue-700 underline">Open Character Studio</a>
        </p>
      )}
    </div>
  )
}

export function LockAndScene({ post, characters, characterRequired, onSetCharacter, onUpdateScene, onBackdropChange, onUseLatestBackdrop, onGenerateImage, loading, error }: Props) {
  const [scene, setScene] = useState(post.scene_instruction ?? '')
  const dirty = scene !== (post.scene_instruction ?? '')
  const noCharacter = post.character_id === null

  useEffect(() => {
    setScene(post.scene_instruction ?? '')
  }, [post.scene_instruction])

  return (
    <section className="post-panel post-panel--scene" aria-labelledby={`scene-${post.id}-heading`}>
      <p id={`scene-${post.id}-heading`} className="post-panel__eyebrow">
        Locked post — derived scene
      </p>

      <pre className="post-copy post-copy--muted">
        {post.post_text}
      </pre>

      <BackdropSelector
        post={post}
        loading={loading}
        onChange={onBackdropChange}
        onUseLatest={onUseLatestBackdrop}
      />

      <div className="post-field">
        <label htmlFor={`scene-${post.id}-details`}>
          Image scene details (advanced)
        </label>
        <textarea
          id={`scene-${post.id}-details`}
          rows={4}
          value={scene}
          onChange={e => setScene(e.target.value)}
        />
        {dirty && (
          <button
            type="button"
            onClick={() => onUpdateScene(scene)}
            className="post-button post-button--secondary post-field__action"
          >
            Save scene edit
          </button>
        )}
      </div>

      {(noCharacter || characterRequired) && (
        <CharacterChoice characters={characters} loading={loading} onSetCharacter={onSetCharacter} />
      )}

      {error && (
        <p className="post-message post-message--danger" role="alert">
          {error}
        </p>
      )}

      <button
        type="button"
        onClick={onGenerateImage}
        disabled={loading || dirty || noCharacter}
        className="post-button post-button--primary post-button--wide"
      >
        {loading ? 'Checking memory…' : 'Generate image'}
      </button>
      {dirty && (
        <p className="post-message post-message--warning">Save your scene edit before generating.</p>
      )}
    </section>
  )
}
