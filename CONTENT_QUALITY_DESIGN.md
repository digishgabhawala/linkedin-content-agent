# Content quality design: categories, pillars, scoring, recalibration

Design lock for the product-direction pivot discussed 2026-07-17. **Status:
built and live-verified** (see TESTING.md) -- this document remains the
design reference/rationale; superseded backlog items #21 (per-character
personas) and #23 (remove clarify cap) are now specific pieces of this
larger design rather than standalone items. The "explicitly deferred"
section at the bottom is still accurate as of this writing -- those pieces
remain unbuilt.

## Vision

Today this tool writes one post from one brief for one hardcoded persona. The
product direction is: a configurable content engine that writes posts for a
person's real voice, in a consistent brand character's world, evaluated against
explicit quality bars before a human ever sees a draft -- while staying strictly
authenticity-first. Reach is a byproduct of quality, never traded for it.

MVP scope is deliberately narrow: one user profile (the current 20-years-experience
persona, now as data instead of hardcoded prompt text), one shared skill.md, the
existing single character. The architecture should not *require* rework to support
N user profiles later, but building multi-tenant config UI/storage now would be
premature -- the file-based split below is enough to get there without a rewrite.

## Three configuration dimensions

Previously conflated into one hardcoded prompt. Now three separate concerns:

1. **User profile** (WHO is speaking) -- experience level, voice, industry,
   expertise. Per-customer eventually; MVP has exactly one (the current user).
   Not a prompt string -- structured enough that pillar scoring can check
   "customer-profile fit" against it.
2. **Character profile** (the brand mascot's personality/POV) -- already exists
   as `CharacterCard` in character-forge-v2, currently underused: its
   `personality` field is placeholder text and has zero influence on how post
   *text* gets written today, only on image scene selection. This design closes
   that gap -- the character becomes a real input to `draft_agent`, not just
   `scene_agent`.
3. **skill.md** (HOW to write well) -- craft rules: hook formulas, structure,
   banned phrases, rhythm checks, authenticity self-test. Shared across all
   users and characters, evolves over time as a single file, not per-customer.
   Content partly informed by the public Claude Skills researched this session
   (kvsdileep/linkedin-writer, sergebulaev/linkedin-skills) -- specifically the
   3-part hook formula, rhythm-variety checks, and pre-output authenticity test
   -- grafted onto our existing factual-accuracy calibration, not replacing it.

## Category (classifies the post, drives pillar weighting -- not itself scored)

Inferred from the brief before drafting. Determines which pillars matter most
for *this* post -- a technical deep-dive and a trending hot-take should not be
graded on the same curve. Deliberately overlaps with `scene_agent`'s existing
implicit mood taxonomy (technical win / frustration / celebratory / reflective /
exploration) -- worth unifying into one shared taxonomy consumed by category
inference, draft scoring, *and* scene derivation, instead of three separate
guesses at the same underlying thing.

1. Technical deep-dive
2. Trending topic / hot take
3. Lessons learned / reflective
4. Milestone / celebration
5. Early-stage exploration
6. Industry opinion / commentary

## Pillars

Two tiers, deliberately not blended into one average -- blending would let a
strong hook score paper over a shaky factual score, which is exactly the
reach-for-authenticity trade that's off the table.

**Gates** (must clear ~9/10; block, never trade off against anything else):
- Factual integrity -- only claims what's in brief/clarify transcript
- Voice authenticity -- passes "would this specific person actually say this,"
  no AI-slop patterns

**Optimization pillars** (scored, weighted by category, recalibrate to maximize):
- Hook strength
- Structure / rhythm
- CTA quality
- Length fit
- Character/brand consistency
- Topic resonance (shareability of the subject itself, distinct from hook
  execution)
- Customer-profile fit
- Market timeliness (near-irrelevant for technical deep-dive, high-weight for
  trending-topic)

Each pillar failure type determines what happens next -- not all failures are
fixable the same way:

| Failure type | Example pillars | Response |
|---|---|---|
| Rewrite-fixable | Hook, structure, CTA, length | Automatic recalibration (rewriting alone can fix it) |
| Needs new material | Factual integrity gate, customer-profile fit | Escalate fast (1 attempt max, not 3) -- ask a *specific* question with a concrete example, since a user usually doesn't know what's missing until shown one |
| Needs a different angle | Topic resonance, market timeliness | Escalate -- rewriting the same topic 3x won't raise it; ask whether to reframe or accept the lower score for this category |

## Judge mechanism

Same model (qwen3:14b via Ollama), distinct system prompt -- not a second model.
Reasoning: our Ollama calls are already stateless (fresh `httpx` POST per call,
no conversation continuity), so the strongest self-grading bias -- the judge
"remembering" it wrote the draft -- mostly doesn't apply already. A genuinely
different model would decorrelate remaining stylistic bias further, but would
mean a second large model loaded in Ollama, directly fighting the RAM-contention
failure mode already root-caused this session (Ollama + ComfyUI competing for
shared unified memory -- see memory note
`agentorg-comfyui-ollama-ram-contention`). Given the human stays the final gate
regardless (see pipeline below), a same-model judge is the right MVP tradeoff.

Mitigations to bake into the judge prompt:
1. Frame it as reviewing someone else's work ("you are a skeptical editor
   grading a draft you did not write"), not self-assessment
2. Explicit rubric text per pillar, not just "rate 1-10"
3. One-line reasoning required per score, not just a number -- auditable by the
   human, not a black box
4. Lower temperature than the writer call (writer ~0.5, judge ~0.1-0.2) for
   consistent, strict grading

Revisit a second/smaller judge model only if the same-model judge is observed
scoring suspiciously generously in practice.

## Pipeline

```
1. Brief in (+ any existing clarify answers)
2. Category inference (brief -> category)
3. Upfront pillar-risk check (NEW, replaces/upgrades today's simple
   "does the brief have >=1 concrete detail" clarify logic):
   given category + brief, anticipate which pillars are AT RISK before ever
   drafting (e.g. a technical-deep-dive brief with no numbers/root-cause is a
   predictable factual-integrity risk; a trending-topic brief with no clear
   personal angle is a predictable topic-resonance risk). If a risk is
   foreseeable, ask ONE targeted question WITH A CONCRETE EXAMPLE of the kind
   of answer that would resolve it -- do this before spending a full
   draft+score cycle, not only after one fails.
4. Draft (draft_agent, now also conditioned on character_profile)
5. Score against gates + category-weighted optimization pillars (judge call)
6. Gates fail, OR a rewrite-fixable pillar is low
     -> automatic recalibration, capped at 3 passes total
7. A needs-new-material or needs-different-angle pillar is low
     -> escalate to human immediately (don't burn automatic passes on
        something a rewrite can't fix) with the specific pillar + example ask
8. After automatic passes are exhausted (or on immediate escalation): surface
   current best draft + exactly which pillars are short and why
9. Human's call, always, no cap here: accept the current post as-is, or
   provide more material/direction and loop back to step 4
```

## Explicitly deferred / not decided here

- Exact numeric pillar weights per category -- needs real drafts to calibrate
  against, not guessable in the abstract
- Exact judge prompt wording / rubric text per pillar
- Whether/how feedback_service's captured feedback (currently capture-only)
  eventually informs pillar weighting or scoring -- out of scope until there's
  real feedback data to look at, consistent with the original capture-only
  decision
- Multi-tenant storage/config UI for N user profiles -- MVP is one profile as
  a file, not a database-backed profile system
- Final unified category/mood taxonomy shared across category inference,
  scoring, and `scene_agent` -- named as a goal above, not yet reconciled
  line-by-line with `scene_agent`'s existing worked examples
