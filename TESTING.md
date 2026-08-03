# What's been verified, and where to see it

## Automated tests

```bash
cd backend
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check .
.venv/bin/pytest tests/ -v

cd ../frontend
npm run lint
npx tsc --noEmit
```

`backend/tests/` covers the deterministic, non-LLM logic in
`post_service.py`, `taxonomy.py`, and `draft_agent.py`'s output cleanup: the
`length_fit` scoring bands, the `@name` scene-asset resolve/expand cycle
(including the retroactive-edit guarantee -- editing an asset after a post
locked must change what that post renders with), pillar-weight sums per
category, and the trailing-metadata/quote-stripping regexes. Uses an
in-memory SQLite fixture, independent of the real app database.

**What automated tests deliberately do NOT cover**: `clarify_turn`,
`generate_draft`/`regenerate_draft`, `score_post`, `infer_category`,
`derive_scene` -- every one of these is a live Ollama call, and the actual
hard-won knowledge in this project (see below) is calibration behavior a
mock would give false confidence about. Those are verified live instead.

## Everything else: verified live, not mocked

Everything below was run live against real Ollama calls, a real SQLite
database, and (for the image path) a real ComfyUI render -- nothing was
mocked except where explicitly noted. This file is the index; the actual
evidence lives in two places:

```bash
git log --oneline          # one commit per task/fix -- each message
                            # documents exactly what was tested and found,
                            # often with specific numbers/examples
git log -p <hash>           # full diff for any specific fix
```

...and in the conversation transcript where the live commands were run
(this repo doesn't persist ad-hoc shell/curl sessions as files).

## Commit-by-commit index

| Commit | What it verified |
|---|---|
| `a14f2cb` Scaffold backend | `init_db()` creates all 3 tables; `uvicorn` boots on :11000; `/api/health` returns 200. |
| `08d8541` feedback_service.py | Real SQLite round-trip: create 2 feedback rows on a post, list returns both in order. |
| `2093f4a` draft_agent.py | Real Ollama calls for clarify/draft/regenerate. **Found and fixed two real bugs** (see "Fabrication bug" below for the fuller story) and a quote-wrapping formatting bug. |
| `8029463` scene_agent.py | Real Ollama calls across debugging/celebratory/reflective moods. **Found and fixed a mood-intensity mismatch** -- see below. |
| `62f9241` Fix: fabrication resurfaced on thin briefs | The SAME fabrication bug came back on a thinner brief than the one used to fix it the first time -- see below. |
| `00471e4` post_service.py | Full real flow: thin brief → clarify question → answer → draft v1 → regenerate → v2 → lock (scene+seed) → finalize correctly gated. Separately verified the clarify-cap forces `drafting` at exactly 3 turns. |
| `6931c15` image_service.py | Validation/concurrency/callback logic tested with `subprocess.Popen` mocked (the real spawn-through-live-callback path was deliberately deferred to the end-to-end pass, see below). |
| `3806acb` routes.py + main.py | Full plumbing verified via real HTTP against a live server: create→clarify→draft→regenerate→drafts→feedback→lock→scene edit→generate-image validation→direct callback simulation→image_ready→finalize→list, plus the 409 guard. |
| `1b735ba` frontend scaffold | `tsc --noEmit` clean, `npm run build` succeeds, live 3-process check confirms `/api` and `/data` both proxy correctly through Vite. **Explicitly NOT verified**: interactive browser click-through -- no browser automation tool was available in the session, so panel transitions/form behavior are unverified beyond what curl/tsc can prove. |
| `02d185b` Fix: retry on a failed image never worked | Found live during the end-to-end pass: `generate-image` on an `image_failed` post always 400'd (only `locked` was accepted). Fixed and re-verified: retry now returns 200 and ComfyUI's queue showed the real job running. |
| `d51172f` Fix: retry replays ComfyUI's cache | Found live: a retry with the ORIGINAL seed came back "successful" in under 20 seconds -- impossible for a real 20B-model render. ComfyUI's own execution history showed every node marked `cached` with `execution_success` timestamp-identical to `execution_cached` -- i.e. zero real compute, it just replayed a previously-cached (corrupted) result. Fixed by forcing a fresh random seed on every retry. |

## The full story: three real bugs found through live testing, not code review

These are worth reading in full because they're the actual reason "test
standalone before wiring in" mattered for this project -- static review
would not have caught any of them.

**1. Draft fabrication.** `draft_agent` was instructed in its system prompt
not to invent facts. On a real Ollama call it did anyway -- given a brief
about fixing an OOM crash with `--low-ram`, it invented "OOM at 30%
completion" and `--mlx-cache-limit-gb=4`, neither of which were stated.
Fixed with a worked correct-vs-wrong calibration example in the prompt.
**Then it came back** on a THINNER brief (less real material = stronger
pull to invent filler) -- fixed with a second calibration example
specifically for thin briefs, plus reinforcing the "don't invent" constraint
in the user turn itself (not just the system prompt), plus a small
temperature drop. Verified against three different unrelated briefs
afterward to confirm generalization, not memorization of the examples.

**2. Scene mood mismatch.** `scene_agent` correctly matched topic to scene
category, but on a genuinely excited milestone post ("crossed 1000 users...
just going to enjoy this one") it produced a flat, muted scene instead of
matching that energy. Fixed with explicit mood-INTENSITY guidance (not just
mood category) and a second celebratory worked example. Re-verified on a
fresh, differently-worded promotion post.

**3. The corrupted-image saga.** This is the big one -- across the whole
end-to-end pass, real renders came back solid black (a ~3KB file instead of
~700KB+) multiple times, with ComfyUI reporting `"status": "success"` and
the callback firing `ok: true` every time. Root causes found, in order:
- Low free system RAM (down to 1.2GB free at one point) starving ComfyUI's
  VAE decode.
- **Ollama itself was the biggest culprit** -- `qwen3:14b` sat loaded in
  memory (14.8GB RSS) from all the draft/scene testing, competing directly
  with ComfyUI for the same unified memory pool. `ollama stop qwen3:14b`
  freed it back to 17.9GB.
- Separately, ComfyUI's own cache replaying a stale corrupted result on
  retry (see `d51172f` above).
- Separately again, after 24+ hours of continuous ComfyUI uptime across many
  load/unload cycles, a genuinely fresh, well-resourced attempt STILL came
  back black -- restarting the ComfyUI process itself fixed it.

**The lesson, stated explicitly because it's easy to skip:** an `ok: true`
callback and a 200 HTTP status do not prove the image is good. Every
"success" in this project was confirmed by actually opening the PNG and
looking at it, not by trusting the API response. The final, genuinely
correct end-to-end render (`e32bf3b2-...` in the test DB, cleaned up after)
was visually confirmed: the correct character, correct pose, correct scene.

## Content-quality pipeline (category/gates/pillars/recalibration)

Built and verified live in a later session than the commit table above (not
yet indexed commit-by-commit here): category inference, gate/optimization
pillar scoring, automatic recalibration, the thin-material escalation gate,
and the deterministic `length_fit` override were all exercised against real
briefs of varying quality (rich briefs producing strong drafts, thin briefs
correctly escalating instead of drafting anyway) and real Ollama judge
calls. The `@name` scene-asset system (recurring backdrops, retroactive
edits) was similarly verified live end-to-end, including rendering real
images through character-forge-v2 with an expanded `@office`-style
reference. See `git log` for the individual commits.

## What is NOT covered

- No interactive browser automation (no such tool was available in the
  build sessions) -- the frontend's build/type-check/lint are clean and its
  API contract is verified, but clicking through the actual UI end-to-end
  has been done manually by the maintainer, not captured as a repeatable
  test. Worth a fresh manual pass before relying on this for real posts.
- The `lightning` speed profile (fast/low-quality image drafts) was never
  exercised -- all real renders used `full`.
- Feedback capture is tested; feedback consumption is not built yet (see
  README's Upcoming section), so there's nothing to test there.
- Pillar weights (`taxonomy.py`) are unweighted starting defaults, not
  calibrated against a body of real drafts yet.
