# What's been verified, and where to see it

No automated test suite exists yet. Every check described here was run live
against real Ollama calls, a real SQLite database, and (for the image path)
a real ComfyUI render -- nothing was mocked except where explicitly noted.
This file is the index; the actual evidence lives in two places:

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

## What is NOT covered

- No automated regression tests (pytest, vitest, or otherwise).
- No interactive browser testing (no browser automation tool was available
  in the build session) -- the frontend's build/type-check is clean and its
  API contract is verified, but clicking through the actual UI has not been
  done by anyone yet. Worth a manual pass before relying on this for real
  posts.
- The `lightning` speed profile (fast/low-quality image drafts) was never
  exercised -- all real renders used `full`.
- Feedback capture is tested; feedback consumption is not built yet (see
  README's Upcoming section), so there's nothing to test there.
