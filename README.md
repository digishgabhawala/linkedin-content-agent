# linkedin-content-agent

Local-first tool that turns "what I worked on today" into a LinkedIn post:
brief → clarify → draft (local LLM) → lock → on-brand character illustration
→ manual review and posting. Built for one person building a LinkedIn
presence around 20 years of software engineering experience, using a
consistent mascot character for visual branding.

This is "System 2" in a two-system split. It never imports
[`character-forge-v2`](../character-forge-v2) ("System 1") -- it shells out
to it as a detached subprocess for the character image, and receives a
callback when the render finishes. Everything else (understanding the brief,
writing the post, deriving what the illustration should show) runs against a
local Ollama model, no cloud dependency.

## Use case

1. You tell it, in your own words, what you did today.
2. If the brief is thin, it asks ONE focused follow-up question (capped at 3
   turns) to get at least one real, checkable detail -- it will not invent
   specifics that weren't given to it.
3. It writes a LinkedIn post in your voice: hook / re-hook / body / CTA
   structure, no AI-slop phrases, grounded only in facts you actually gave
   it.
4. You can revise it with a free-text instruction ("shorter hook", "more
   technical"), or start over, as many times as you want -- every version is
   kept.
5. When you lock a draft, it derives a terse visual scene description for
   the character illustration (e.g. "presenting a chart on a whiteboard,
   calm confident energy") -- you can edit this before rendering.
6. Generating the image is a real 15-40 min local render (System 1 /
   ComfyUI) -- the app doesn't block on it; you can leave and come back.
7. Once the image is ready, review text + image together and mark the post
   ready. Posting to LinkedIn itself is manual (copy the text, download the
   image) -- this tool doesn't publish anything for you.
8. You can leave feedback at any stage. It's stored, but **not yet fed back**
   into future drafts -- see Upcoming below for why.

## Prerequisites

- Python 3.10+, Node 18+
- [Ollama](https://ollama.com) running locally with `qwen3:14b` pulled:
  ```bash
  ollama pull qwen3:14b
  ```
- **[`character-forge-v2`](../character-forge-v2) set up and working**,
  including its own prerequisite (a running ComfyUI with the right models),
  since this app spawns it as a subprocess for every image render. At least
  one character must already have a locked `hero.png` (the shipped default,
  `gtee_dev`, is already seeded there).
- Ports `11000` (backend) and `11001` (frontend) free.

## Setup

**Backend:**
```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # defaults work out of the box on this machine
.venv/bin/uvicorn app.main:app --port 11000
```

**Frontend** (separate terminal):
```bash
cd frontend
npm install
npm run dev
# -> http://localhost:11001
```

Open `http://localhost:11001` and start with a brief.

## Configuration

All backend config lives in `backend/.env` (see `.env.example`):

| Key | Default | What it does |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_MODEL` | `qwen3:14b` | model used for clarify/draft/regenerate/scene |
| `DB_PATH` | `posts.db` | SQLite file (created automatically) |
| `DATA_DIR` | `data` | where rendered images + placeholder live, served at `/data` |
| `DEFAULT_CHARACTER_ID` | `gtee_dev` | which character-forge-v2 character to use |
| `CLARIFY_MAX_TURNS` | `3` | max clarify questions before forcing a draft anyway |
| `CHARACTER_FORGE_V2_PATH` | *(auto-resolved absolute path)* | only set if your layout differs from the standard sibling-directory tree |
| `COMFYUI_ENV_PYTHON` | *(auto-resolved absolute path)* | same |
| `IMAGE_CALLBACK_BASE_URL` | `http://localhost:11000` | where the forge2 subprocess POSTs back to when done |
| `IMAGE_STALL_TIMEOUT_MINUTES` | `40` | past this with no callback, the UI flags the render as possibly stalled |

`CHARACTER_FORGE_V2_PATH`/`COMFYUI_ENV_PYTHON` resolve automatically to the
correct absolute sibling paths (computed from this file's own location) --
you should not need to touch them unless you've moved things around.

## Known issues / operational notes

- **Image generation is genuinely slow (15-40 min)** and depends entirely on
  character-forge-v2/ComfyUI being healthy -- see that repo's README for the
  RAM-pressure and stale-ComfyUI-state failure modes found during testing.
  If a render comes back with a solid-black/corrupted image despite
  `image_ready` status, the underlying render failed silently; there is
  currently **no automatic detection of this** (see Upcoming).
- **Retrying a failed image assigns a fresh seed automatically** -- reusing
  the same seed would just replay ComfyUI's cached (possibly corrupted)
  result instead of rendering again. This is handled for you; you don't need
  to do anything manually.
- **No way to re-roll an image once it reaches `image_ready`.** The Retry
  button only appears (and only works) when a render explicitly failed
  (`image_failed`). If a render technically succeeds but looks wrong on
  inspection, there's currently no in-app way to trigger a fresh attempt --
  found this gap during testing (see Upcoming).
- Only one image can render at a time (single-GPU pipeline) -- starting a
  second one while one is in flight returns a 409.

## Upcoming / backlog (not built yet)

- **Feedback consumption.** Feedback is captured (stage, note, timestamp)
  but deliberately not yet fed back into prompts -- different post
  categories (technical deep-dive vs. quick update vs. commentary) likely
  need different feedback semantics, and designing that taxonomy before
  seeing real feedback data would be guessing. Ship capture, observe, design
  later.
- **Regenerate/re-roll an image from `image_ready`.** Currently only a
  genuinely failed render can be retried; a technically-successful-but-bad
  render has no re-roll path in the UI yet.
- **Pre-flight RAM check** and **automatic corrupted-image detection +
  ComfyUI auto-restart** -- shared backlog items with character-forge-v2,
  see that repo's README for detail.
- **Real per-character personas.** The character brief's `personality`
  field is still placeholder text; the original vision (e.g. a green-shirt
  character that explains things, a red one that asks security questions, a
  blue one that asks ROI questions) hasn't been designed yet.
- **Multi-character support beyond the one seeded character (`gtee_dev`).**

## Project layout

```
backend/app/
  config.py                 -- Settings (env-driven, see table above)
  db/models.py               -- Post, PostDraft, Feedback (SQLAlchemy)
  agents/draft_agent.py      -- clarify_turn, generate_draft, regenerate_draft (Ollama)
  agents/scene_agent.py      -- derive_scene (post text -> terse visual scene, Ollama)
  services/post_service.py   -- Post state machine (clarify cap, draft versioning, lock)
  services/image_service.py  -- subprocess.Popen spawn + callback receiver + stall detection
  services/feedback_service.py -- capture-only create/list
  api/routes.py               -- all HTTP routes, including /api/internal/image-callback
  main.py                     -- FastAPI app, mounts /data

frontend/src/
  App.tsx                     -- top-level state-machine controller
  api.ts, types.ts             -- typed client matching routes.py exactly
  hooks/usePostPolling.ts      -- 3s polling, only while status === image_queued
  components/                  -- one component per Post.status (see App.tsx)
```

Post status flow: `clarifying → drafting → locked → image_queued →
image_ready | image_failed → ready`
