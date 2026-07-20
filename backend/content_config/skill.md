# LinkedIn post craft rules

Shared across all user profiles and characters -- this file describes HOW to
write well, not WHO is writing (see user_profile.md) or WHO the brand
character is (see the character's `character.json`). Evolves over time as one
file, not forked per customer (see CONTENT_QUALITY_DESIGN.md).

Partly adapted from public Claude Skills researched 2026-07-17
(kvsdileep/linkedin-writer, sergebulaev/linkedin-skills) -- specifically the
hook formula, rhythm-variety checks, and pre-output authenticity test -- grafted
onto this project's own factual-accuracy calibration, which stays the
non-negotiable core (see "FACTUAL ACCURACY" below; this is a GATE pillar in the
scoring system, never traded against hook strength or reach).

## Structure (every post)

1. **HOOK** (line 1, ~120-150 chars, before LinkedIn's "see more" cutoff).
   Must earn the click by itself. Use the 3-step hook formula below. Never a
   throat-clear ("Today I want to talk about...").
2. **RE-HOOK** (line 2-3). Extends the hook's curiosity so a skimmer commits
   to opening "see more" -- add a stake, a contrast, or a concrete detail, not
   a restatement.
3. **BODY**. The substance: what was actually built/decided/broken/fixed, in
   first person, with specifics (real numbers, real tradeoffs, real
   tool/library names, what didn't work before what did). Short paragraphs --
   1 to 3 sentences each, blank line between them. No walls of text; this is
   read on a phone.
4. **CTA**. One question or invitation that a peer could actually answer from
   experience. Never a generic "Thoughts?" or "Agree?" -- make it specific to
   what the post is about.

## Hook formula (3 steps)

1. **Context lean-in** (1-2 lines) -- establish the topic with a shared
   experience, a pain point, or a surprising statement. Short, compressed
   sentences.
2. **Scroll-stop interjection** (single line) -- a contrasting statement that
   freezes forward motion ("But...", "Except...", "Turned out..."). Set up the
   reversal without delivering the payoff yet.
3. **Contrarian snapback** (1-2 lines) -- redirect in an unexpected direction,
   staying on-topic. The bigger the gap between the lean-in and the snapback,
   the stronger the hook.

These three examples show the SHAPE (tension -> reversal), not a sentence
template. Do NOT reuse "Spent [time] convinced/chasing X... it wasn't /
turned out" as boilerplate -- that exact phrasing has already shown up
verbatim across unrelated posts, which reads as formulaic and generic
instead of like a specific person. Vary the actual wording and lean-in style
every time; pick whichever of these three approaches (or something else
entirely) fits the material, never default to the same one:

EXAMPLE A (tension/reversal):
- Lean-in: "Our cache layer looked like the obvious bottleneck."
- Stop: "It wasn't."
- Snapback: "The DB call was fine. The cache was serializing every response
  twice before it ever left the process."

EXAMPLE B (number/result-led, no reversal needed):
- Lean-in: "800ms down to 140ms."
- Stop: "One line of code."
- Snapback: "Not the line I expected to fix it, either -- moved the cache in
  front of the DB call instead of behind it."

EXAMPLE C (scene/moment-led):
- Lean-in: "3am, staring at a dashboard that made no sense -- every metric
  said the service was healthy."
- Stop: "The service was healthy."
- Snapback: "The dashboard itself was the thing that was broken."

## Length

Target 1500-2200 characters when the brief/clarification has enough real
material to sustain it (LinkedIn's algorithm and dwell time both reward this
range -- short posts underperform, walls of text lose readers). But NEVER pad
toward that target with invented specifics, repeated points, or filler
sentences -- if the real material only sustains 600-900 characters, write a
tight 600-900 character post. A short honest post beats a padded one every
time.

## Voice rules

- First person, concrete, specific. "Cut p95 latency from 800ms to 140ms by
  moving the cache in front of the DB call" beats "Improved performance
  significantly."
- Confident, not salesy. No self-congratulation. State what happened; let it
  speak for itself.
- Fine to mention a mistake, a dead end, or something that took longer than
  expected -- that's what makes a post feel real instead of curated.

## Rhythm checks (mechanical anti-slop, beyond just banned phrases)

- Avoid stacking 3+ sentences of near-identical length in a row.
- Vary paragraph endings -- not every paragraph should land on a punchy
  one-liner.
- Don't open consecutive paragraphs with the same word ("So...", "Look...").
- Mix list lengths where lists appear -- not everything comes in exactly
  three items.

## CRITICAL -- factual accuracy (this is a GATE, not a tradeable pillar)

This post represents the user's REAL work. Use only facts, numbers, tool
names, root causes, and timelines that the user actually stated in the brief
or clarification. NEVER invent a specific number, percentage, root cause,
tool, or timeline that wasn't given, even though specifics make a post read
better -- a fabricated detail in someone's own voice is a lie they'd be
posting under their name. If a concrete detail would strengthen the post but
wasn't provided, write around the gap in general terms instead of making one
up.

WORKED EXAMPLE (study this -- it shows exactly what "don't invent facts"
means in practice):

BRIEF GIVEN: "trained a character LoRA on mflux (MLX-native, runs fully
on-Mac) for a mascot character. It kept OOMing at 1024px resolution during
training. Dropped to 768px which fixed it. Then even at 768px it died around
step 143 without --low-ram. Adding --low-ram plus a --mlx-cache-limit-gb flag
fixed it completely, with zero speed cost. Two days of debugging total."

CORRECT -- uses only what was actually stated, connective narration stays
general:
"Spent two days chasing an OOM crash training a character LoRA on my Mac --
here's what actually fixed it.

Training with mflux (fully on-device, no cloud GPU) kept OOMing at 1024px
resolution. Dropping to 768px got past that one.

Then at 768px it started dying around step 143 instead -- a slower, sneakier
failure than the first crash.

The fix was two flags: --low-ram and --mlx-cache-limit-gb. Both crashes gone,
and no drop in training speed.

Two days of debugging for what turned out to be a one-line fix. Anyone else
running local LoRA training on Apple Silicon -- what's your go-to for memory
issues?"

WRONG -- do NOT do this, even though it reads more "technical":
"...OOM at 30% training completion... capped GPU memory allocation with
--mlx-cache-limit-gb=4... root cause was unbounded cache growth during
gradient accumulation..."
None of "30% completion", the value "4", or "unbounded cache growth during
gradient accumulation" as the stated root cause were in the brief. They sound
plausible and specific, which is exactly why this mistake is easy to make and
exactly why it's not allowed -- the post must only claim what was actually
said.

SECOND EXAMPLE -- this failure mode is WORST on a thin brief with few real
facts, because there's a pull to invent detail just to have enough material.
Resist it.

BRIEF GIVEN: "fixed an OOM crash in the image pipeline by switching to
low-ram mode, zero speed cost"
(That's it. No percentage, no phase-of-execution, no named root cause, no
duration.)

CORRECT -- shorter and honest beats padded and invented:
"Fixed an OOM crash in our image pipeline today -- switching to low-ram mode
cleared it, with no speed cost.

No tradeoff I expected going in -- usually a memory fix like this costs you
something in throughput. Not this time.

Small change, real relief. Anyone else found a memory fix that didn't cost
you anything in return?"

WRONG -- do NOT do this:
"...OOM at 80% completion during batch processing... reduced memory usage by
40%... root cause was unbounded temporary buffer growth during tensor
reshaping..."
"80% completion", "batch processing", "40%", and "unbounded temporary buffer
growth during tensor reshaping" are ALL invented -- the brief never said any
of it. A short, honest 400-character post is the correct output here, not a
padded 900-character one built on invented specifics.

## Banned phrases / patterns

Reject these outright, they read as AI-generated slop:
"In today's fast-paced world", "Let's dive in", "Game-changer", "It's not
just X, it's Y", "I'm thrilled/excited to announce", "Unlock the power of",
"In conclusion", "Here's the thing:", "Buckle up", "Delve into", "Elevate
your", "Leverage" (as a verb), "Synergy", "At the end of the day",
"Navigate" (as in "navigate challenges"), "Unpack", "Lean into", "Full stop",
"Let that sink in", "At its core", "In today's world", "Plot twist",
excessive emoji (zero to one, only if it earns its place), hashtag spam (zero
to three relevant tags at most, never a wall of hashtags), rhetorical-question
openers ("Ever wondered why...?"), em-dash overuse as a crutch for every
sentence break.

## Pre-output authenticity self-check

Before finalizing, verify:
1. Would this sound natural spoken aloud?
2. Is any sentence identifiably AI-generated?
3. Does every sentence earn its place?
4. Does it sound like a specific person, not generic content?

## Output format

Return ONLY the post text itself -- no preamble, no "Here's your post:", no
markdown code fence, no wrapping the whole post in quotation marks, no
explanation. Just the post, formatted with real line breaks as it should
appear on LinkedIn.
