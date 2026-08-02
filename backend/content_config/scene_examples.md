# scene_examples.md

Worked examples for scene_agent.py, grouped by mood archetype. A RANDOM SUBSET
(one example from a random sample of archetypes) is injected per call by
content_sources.py's `load_scene_examples()` -- never the full file, and never
the same fixed set twice.

**Why rotation, not a fixed list:** the original scene_agent shipped with one
fixed example per archetype, always shown in the same order. Found live
(2026-07-31): the model echoed the "office/monitor/bar-chart" example nearly
verbatim for an unrelated post, just because that post's mood loosely matched
"analytical." Same root cause as the hook-template and factual-accuracy
over-anchoring bugs found earlier in draft_agent -- a single memorable
worked example becomes a template, not a style reference. Rotation is the
fix, same as example_posts.md's own docstring explains for the writer.

**If you add more examples, preserve this:** each archetype needs at least 2
examples with genuinely different `action`/`setting_name` choices, not just
reworded versions of the same image -- otherwise rotation doesn't actually
prevent anchoring, it just anchors on a slightly larger fixed set.

Output schema per example (matches scene_agent's structured output):
`{"action": str, "setting_name": str|null, "setting_detail": str|null, "angle": str, "mood": str}`

`setting_name` is a short lowercase slug for a REAL RECURRING PLACE (office,
coffee_shop, home_desk) -- set to `null` when the scene is built around a
one-off symbolic object/action instead (dominoes, mirror, confetti), where
the backdrop is incidental and not worth remembering as a named asset.

---

## MOOD: calm_technical_win

### Example 1
POST: "Cut p95 latency from 800ms to 140ms by moving the cache in front of the DB call instead of behind it. Took a week to find, one line to fix."
SCENE: {"action": "presenting a chart on a whiteboard, calm confident energy", "setting_name": "office", "setting_detail": "glass-walled meeting cabins visible in the background, a wall clock with a blank face, a whiteboard covered in diagram sketches and arrows, a closed laptop on a nearby desk", "angle": "three-quarter view", "mood": "calm, confident"}

### Example 2
POST: "Found the exact line causing a memory leak that had been creeping up for weeks. One unclosed file handle in a retry loop. Fixed, and memory usage is flat now."
SCENE: {"action": "closing a laptop with a satisfied nod, one hand still on the lid", "setting_name": "home_desk", "setting_detail": "a single monitor showing an abstract line graph, no numbers or text, a plant on the windowsill, warm afternoon light through the window", "angle": "side view", "mood": "quiet satisfaction"}

---

## MOOD: frustration_debugging

### Example 1
POST: "Spent the whole day chasing a race condition that only reproduced under load. Turned out to be a missing mutex around a shared counter."
SCENE: {"action": "facepalming at a laptop, screen dim, shoulders slumped", "setting_name": "office", "setting_detail": "glass-walled meeting cabins visible in the background, a wall clock with a blank face, a whiteboard covered in diagram sketches and arrows, a closed laptop on a nearby desk", "angle": "front view", "mood": "frustrated, dim lighting"}

### Example 2
POST: "Three failed deploys in a row today. Every fix revealed the next thing that was broken. Finally got it stable at 11pm."
SCENE: {"action": "rubbing temples, staring at a dark screen, tense posture", "setting_name": "home_desk", "setting_detail": "a single monitor showing an abstract line graph, no numbers or text, a plant on the windowsill, warm afternoon light through the window", "angle": "three-quarter view", "mood": "exhausted, late-night"}

---

## MOOD: analytical_reviewing

### Example 1
POST: "Set up a local system that reviews my conversations and gives feedback on what could have gone better, broken down by type and role."
SCENE: {"action": "pointing at a wall of printed charts and sticky notes, studying them closely", "setting_name": "office", "setting_detail": "glass-walled meeting cabins visible in the background, a wall clock with a blank face, a whiteboard covered in diagram sketches and arrows, a closed laptop on a nearby desk", "angle": "side view", "mood": "analytical, focused"}

### Example 2
POST: "Built a dashboard that tracks all my metrics in one place. Finally have visibility into what matters."
SCENE: {"action": "sitting forward, tracing a finger along an abstract line graph on a monitor, no numbers or text", "setting_name": "home_desk", "setting_detail": "a single monitor showing an abstract line graph, no numbers or text, a plant on the windowsill, warm afternoon light through the window", "angle": "three-quarter view", "mood": "engaged, curious"}

---

## MOOD: celebratory_ship

### Example 1
POST: "Shipped the v2 migration tonight after three weeks of work. Zero downtime, all tests green. Team pulled together hard for this one."
SCENE: {"action": "celebrating with confetti falling, arms raised", "setting_name": null, "setting_detail": null, "angle": "front view", "mood": "elated, evening"}

### Example 2
POST: "Finally merged the PR that's been open for a month. Bigger relief than I expected."
SCENE: {"action": "leaning back in a chair, fist pump, big grin", "setting_name": "office", "setting_detail": "glass-walled meeting cabins visible in the background, a wall clock with a blank face, a whiteboard covered in diagram sketches and arrows, a closed laptop on a nearby desk", "angle": "three-quarter view", "mood": "relieved, triumphant"}

---

## MOOD: celebratory_milestone

### Example 1
POST: "After six months of nights and weekends, my side project just crossed 1000 users. No marketing budget, just word of mouth. Tonight I'm just going to enjoy this one."
SCENE: {"action": "celebrating with arms raised, big smile, confetti falling", "setting_name": null, "setting_detail": null, "angle": "front view", "mood": "genuinely excited, evening"}

### Example 2
POST: "Hit our first $10k month today. Started this as a side hustle 8 months ago questioning if it would ever work."
SCENE: {"action": "punching the air with one fist, wide grin, standing up from a chair", "setting_name": "home_desk", "setting_detail": "a single monitor showing an abstract line graph, no numbers or text, a plant on the windowsill, warm afternoon light through the window", "angle": "three-quarter view", "mood": "triumphant, bright"}

---

## MOOD: reflective_lessons

### Example 1
POST: "Twenty years in and the lesson that keeps repeating: the bug is almost never where you first look. Slow down, reproduce it, THEN theorize."
SCENE: {"action": "reading a thick book in an armchair", "setting_name": null, "setting_detail": null, "angle": "side view", "mood": "thoughtful, warm lamp light"}

### Example 2
POST: "The biggest thing I got wrong early in my career was believing more abstraction always meant better code. Now I wait until I have two real use cases before abstracting anything."
SCENE: {"action": "looking out a window, one hand on the glass, contemplative", "setting_name": "office", "setting_detail": "glass-walled meeting cabins visible in the background, a wall clock with a blank face, a whiteboard covered in diagram sketches and arrows, a closed laptop on a nearby desk", "angle": "side view", "mood": "quiet, reflective"}

---

## MOOD: exploration_early_stage

### Example 1
POST: "Two days into prototyping a new pipeline. Still figuring out the right shape for it, but the early signal is promising."
SCENE: {"action": "looking at a wall of sticky notes, back view, thinking", "setting_name": null, "setting_detail": null, "angle": "back view", "mood": "curious, thinking"}

### Example 2
POST: "Started sketching out ideas for a new internal tool this week. Nothing concrete yet, just seeing what shape the problem actually has."
SCENE: {"action": "sketching in a notebook, pen mid-stroke, leaning over the page", "setting_name": "home_desk", "setting_detail": "a single monitor showing an abstract line graph, no numbers or text, a plant on the windowsill, warm afternoon light through the window", "angle": "three-quarter view", "mood": "early, open-ended"}

---

## MOOD: iterative_struggle

### Example 1
POST: "Every fix revealed another blind spot -- the generator kept reflecting my own assumptions back at me. It felt like a game of whack-a-mole between automation and control, with no clean resolution in sight."
SCENE: {"action": "resetting toppled dominoes one at a time, focused", "setting_name": null, "setting_detail": null, "angle": "side view", "mood": "focused, evening, dim desk lamp"}

### Example 2
POST: "Kept tuning the same config for a week. Fix one metric, another one gets worse. Feels like squeezing a balloon."
SCENE: {"action": "juggling with a strained expression, one ball about to drop", "setting_name": null, "setting_detail": null, "angle": "front view", "mood": "strained, determined"}
