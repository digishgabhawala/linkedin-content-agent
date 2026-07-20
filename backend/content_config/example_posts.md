# Example posts, five per category

Curated gold-standard examples for CONTENT_QUALITY_DESIGN.md's category
taxonomy. Two jobs:

1. **Writer few-shot** (`draft_agent.py`): ONE randomly-chosen example from
   the CURRENT post's category is injected as a style reference alongside
   skill.md -- deliberately one, not all five, so the writer isn't diluted
   across styles it doesn't need right now. The random choice is itself the
   point: across many posts in the same category, the style anchor rotates
   instead of always being the same one example, which is what caused the
   2026-07-18 over-anchoring bug in the first place (see
   linkedin-content-agent-product-pivot memory note).
2. **Judge calibration** (`judge_agent.py`): a broader sample across all six
   categories, with their score emphasis, is baked in statically so the
   judge understands that "good" means something different per category
   BEFORE it grades anything.

Each of the 5 examples WITHIN a category deliberately uses a different hook
shape too (number-led, contrarian-claim, flat-statement, scene/moment-led,
observation-led, reaction/quote-led) -- variety has to hold within a
category, not just across categories, or the same over-anchoring risk
reappears one level down. If you add more examples later, keep it varied.

---

## CATEGORY: technical_deep_dive

### Example 1 (number-led)

Query took 4.2 seconds. Should've taken 40 milliseconds.

Turned out the ORM was silently ignoring a composite index because of a type
mismatch in one join column -- varchar on one side, text on the other.
Postgres just didn't use it, no error, no warning.

Fixed the column type. Query time dropped back to 38ms. No code changes, no
query rewrite.

Anyone else lost hours to a silent index miss that had nothing to do with
the query itself?

*Score emphasis:* `profile_fit` 10, `hook` 9 (sharp number contrast),
`market_timeliness` 10 (n/a for this category), `topic_resonance` 8 (niche
but real).

### Example 2 (contrarian-claim)

Everyone on the team assumed the slow endpoint was a database problem.

It was the JSON serializer. We were re-serializing the same nested object
graph three times per request -- once for the API response, once for the
audit log, once for a cache key. Collapsed it to one pass.

Response time dropped by more than half. Not a single query changed.

Ever had a performance fix that had nothing to do with the layer everyone
blamed first?

*Score emphasis:* `hook` 9 (subverts the team's own assumption), `structure`
9, `profile_fit` 9.

### Example 3 (scene-led)

Watching a deploy roll out at 2am, waiting for error rates to spike the way
they always did on this service.

They didn't.

Six months of chipping away at a flaky integration test suite, one root
cause at a time, finally added up to a deploy that just worked, without
anyone babysitting it.

No single fix did this. It was maybe thirty small ones, none of which felt
significant on their own.

What's the least glamorous fix that quietly made the biggest difference for
you?

*Score emphasis:* `voice_authenticity` 9 (resists the urge to claim one
dramatic fix), `character_consistency` 8, `length_fit` 8.

### Example 4 (flat-statement)

Our retry logic was making the outage worse, not better.

Every failed request was retrying three times with no backoff, which meant
a struggling service got hit with 4x the load right when it needed the
opposite. Classic thundering herd, and we'd built it ourselves.

Added exponential backoff with jitter. The next partial outage recovered in
minutes instead of the better part of an hour.

Anyone else built a safety mechanism that turned out to be the thing making
incidents worse?

*Score emphasis:* `hook` 9 (irony-forward claim), `factual_integrity` 10
(specific mechanism named, not vague), `cta` 9.

### Example 5 (observation-led)

Noticed our build times had crept up to nine minutes and nobody had
actually looked at why in over a year.

Turned out half of it was a test suite importing a full ML dependency just
to check that a config flag existed. Swapped the check for a plain file
read.

Nine minutes down to just under four. No test coverage lost.

What's sitting in your build pipeline right now that nobody's questioned in
a while?

*Score emphasis:* `topic_resonance` 8, `profile_fit` 9, `length_fit` 9
(tight, no padding).

---

## CATEGORY: trending_topic

### Example 1 (contrarian-claim)

Everyone's benchmarking the new model on coding leaderboards this week.

I don't care about the leaderboard number. I care about one thing: does it
still remember what I told it three files ago.

Ran my usual test -- a multi-file refactor where context tracking matters
more than raw capability. It held on longer than the last two releases
combined.

That's the benchmark that actually predicts whether I'll use it Monday
morning, not the synthetic score.

What's your actual go/no-go test for a new model release?

*Score emphasis:* `market_timeliness` 10, `topic_resonance` 9, `hook` 9.

### Example 2 (number-led)

Three new coding models launched this month. I tried all three on the same
real refactor.

Only one of them didn't break a working test while "fixing" an unrelated
function.

That's the whole review, honestly -- benchmark scores didn't predict which
one respected the boundary of what I actually asked it to touch.

Which of the new releases have you actually trusted with a real change, not
just a demo?

*Score emphasis:* `market_timeliness` 9, `profile_fit` 8 (hands-on test, not
opinion), `hook` 8.

### Example 3 (observation-led)

Watched the discourse this week split into two camps: people who think the
new pricing change kills small projects, and people who think it barely
matters.

Ran the numbers on our own usage. It's closer to a 15% cost shift for us --
annoying, not fatal, and probably a rounding error for anyone bigger.

The loud reactions on both sides are talking about different scales of
project, past each other.

Where does your actual usage land -- rounding error or real budget
conversation?

*Score emphasis:* `market_timeliness` 10, `factual_integrity` 9 (grounds the
take in the person's own numbers), `topic_resonance` 8.

### Example 4 (flat-statement)

The new framework release everyone's excited about this week doesn't fix
the thing that actually slows my team down.

Compile times, sure, marginally better. But our bottleneck has never been
compile time -- it's onboarding new engineers into an inconsistent module
structure, and no framework release touches that.

Excited for the win. Just not the win we needed.

What's the gap between what's trending this week and what your team
actually needs?

*Score emphasis:* `hook` 8 (deflates the hype without dismissing it),
`voice_authenticity` 9, `market_timeliness` 9.

### Example 5 (reaction-led)

"This changes everything" -- said about every major model release for two
years running now.

This one's actually a little different, but not for the reason the
headlines are using: it's the first one that admitted uncertainty in its own
output instead of confidently guessing.

That's a smaller feature than "changes everything," and a much more useful
one for anything production-facing.

What's the last release that actually changed your workflow, not just your
feed?

*Score emphasis:* `hook` 9 (opens on a quote to undercut it), `voice_authenticity`
8, `market_timeliness` 9.

---

## CATEGORY: lessons_learned

### Example 1 (flat-statement)

Twenty years in, and the debugging habit that's saved me the most time
isn't a tool. It's a rule: reproduce before you theorize.

Early in my career I'd read a stack trace and immediately start forming a
root-cause story. Half the time I'd fix the wrong thing, confidently.

Now the first move is always: can I make this happen on demand, in front of
me. If I can't reproduce it, I don't understand it yet -- I'm just guessing
with extra steps.

Slower in the first five minutes. Faster every minute after that.

What's the one habit that took you years to actually believe?

*Score emphasis:* `profile_fit` 10, `voice_authenticity` 9, `hook` 8
(wisdom-statement shape is correct here, not tension-driven).

### Example 2 (scene-led)

Sat in a postmortem fifteen years ago where the senior engineer in the room
said "blameless doesn't mean consequence-free" -- and it's the line I still
think about most.

Blameless means we don't punish the person who found the bug in production.
It doesn't mean nothing changes about the process that let it ship.

I've watched teams use "blameless" as a reason to skip the second half of
that sentence.

Where's the line between blameless and accountable landed on your team?

*Score emphasis:* `hook` 9 (borrowed quote grounds the whole post),
`profile_fit` 9, `topic_resonance` 8.

### Example 3 (contrarian-claim)

Everyone tells junior engineers to ask more questions.

The habit that actually made me better was the opposite: sitting with a
confusing problem for twenty minutes before asking anyone anything.

Not because questions are bad. Because most of what I thought I needed to
ask, I ended up answering myself by the time I understood the question I
wanted to ask.

Now I coach the same twenty-minute rule -- ask, but only after you've tried
to answer it yourself first.

What's a piece of advice you had to unlearn to get better?

*Score emphasis:* `hook` 9 (contradicts common advice, earns it with
reasoning), `voice_authenticity` 9.

### Example 4 (number-led)

Three companies, three different outages, one identical root cause: a
config value that was correct in every environment except the one that
mattered.

Different systems, different stacks, same failure shape every time.

I don't trust config parity between environments anymore -- I verify it,
every time, as part of the actual deploy, not as a one-time setup step.

What's the failure pattern you've seen repeat across completely unrelated
jobs?

*Score emphasis:* `profile_fit` 10 (pattern only visible across a long
career), `factual_integrity` 9, `hook` 8.

### Example 5 (flat-statement)

The best code review comment I ever got wasn't about my code. It was "what
happens if this runs twice."

I hadn't thought about it. It wasn't idempotent, and it would have silently
double-charged something under retry.

Twenty years later it's still the first question I ask on anything that
touches money or state.

What's the one review question that's stuck with you the longest?

*Score emphasis:* `hook` 9 (specific quoted question, not generic wisdom),
`voice_authenticity` 8, `length_fit` 9.

---

## CATEGORY: milestone

### Example 1 (direct/celebratory)

Just crossed 1,000 users on a side project I almost shut down twice.

No marketing budget. No launch post that went viral. Just word of mouth, one
frustrated Slack message at a time.

The version that's live today barely resembles the first one -- rebuilt the
core twice because I was wrong about what people actually needed, both
times.

Tonight I'm just going to sit with this one for a bit before I start
planning what's next.

To anyone in the middle of the "should I kill this" phase right now -- keep
going a little longer.

*Score emphasis:* `character_consistency` 9, `hook` 9, `topic_resonance` 9.

### Example 2 (number-led)

Zero to forty paying customers in four months, with a product I almost
didn't build because I assumed the market was already too crowded.

Turns out crowded and served aren't the same thing -- there was a specific
workflow nobody else had bothered to support well.

Still small. Still real. Still the first time revenue from something I
built has covered its own hosting bill.

What was the assumption that almost stopped you from starting?

*Score emphasis:* `hook` 9, `voice_authenticity` 8 (undersells rather than
oversells "still small"), `character_consistency` 8.

### Example 3 (scene-led)

Stood in the office at 11pm after the migration finished, just watching the
dashboard stay green.

Eighteen months of incremental work led to this one boring, uneventful
cutover -- no rollback, no incident channel, no 3am page.

Boring is the whole point. Boring means it worked.

Didn't announce this anywhere else. Just wanted to write it down.

What's a win you were proud of that nobody outside your team ever heard
about?

*Score emphasis:* `voice_authenticity` 9 (celebrates "boring" instead of
manufacturing drama), `hook` 8, `character_consistency` 7.

### Example 4 (flat-statement)

Our open-source project just hit its 500th external contributor.

Started as an internal tool three of us wrote to solve our own problem,
released almost as an afterthought.

The maintenance burden is real and nobody warns you about that part. But
five hundred people found enough value in something we almost didn't
publish to show up and improve it.

What made you decide to open-source something you built for yourself?

*Score emphasis:* `hook` 8, `topic_resonance` 9, `voice_authenticity` 8
(names the real cost, not just the win).

### Example 5 (observation-led)

Looked back at the roadmap from a year ago today while writing the retro
for what we actually shipped.

We hit maybe 40% of what we planned -- and the 60% we didn't do included at
least three things I'm relieved we skipped once I saw how the year actually
unfolded.

Shipped less than planned, built more of what mattered. Calling that a win.

Anyone else had a year where missing the plan turned out to be the right
call?

*Score emphasis:* `hook` 8 (reframes a "miss" as the milestone),
`voice_authenticity` 9, `character_consistency` 7.

---

## CATEGORY: exploration

### Example 1 (status-marker)

Three days into prototyping a new ingestion pipeline and I still don't know
if the shape is right.

Started with a queue-per-source design. Now leaning toward a single shared
queue with source tagging -- fewer moving parts, but I'm not sure yet if
it'll hold up under real load.

No strong opinion to share here, just the actual state of things: promising,
unproven, still changing daily.

Anyone gone back and forth on queue-per-source vs. shared-queue-with-tagging?
What made you pick one?

*Score emphasis:* `voice_authenticity` 9, `length_fit` 9, `hook` 7
(deliberately lower-intensity).

### Example 2 (flat-statement)

Not sure yet if this new approach to background job scheduling is actually
better or just different.

Moved from a cron-based system to an event-driven one this week. Fewer
moving parts on paper. More places a message can get silently dropped in
practice, at least so far.

Genuinely undecided. Watching failure rates for another week before I trust
my own instinct here.

Anyone made this same move and regretted it, or been glad they did?

*Score emphasis:* `voice_authenticity` 9 (states uncertainty as the actual
finding), `hook` 7, `length_fit` 8.

### Example 3 (scene-led)

Whiteboard is covered in three different versions of the same data model
and I've erased and redrawn it twice today.

The tension is between query simplicity and write complexity, and every
version I sketch solves one at the cost of the other.

No conclusion yet. Just documenting that this is what week one of a hard
design problem actually looks like -- messy, not confident.

How do you usually break a tie between two designs that are both
defensible?

*Score emphasis:* `voice_authenticity` 9, `hook` 8, `character_consistency`
7.

### Example 4 (number-led)

Two prototypes, one real workload, and so far a coin flip on which one
wins.

Prototype A is faster on reads. Prototype B is faster on writes. Our actual
traffic is close enough to 50/50 that the benchmark isn't telling me
anything decisive yet.

Going to let both run against shadow traffic for another week rather than
guess.

When benchmarks tie, what tips your decision?

*Score emphasis:* `hook` 8, `factual_integrity` 9 (specific, ungimmicked
comparison), `length_fit` 9.

### Example 5 (observation-led)

Noticed I've rewritten the same fifty lines of onboarding code four times
this month, each time convinced the previous version was wrong.

Might mean I still don't understand the actual requirements. Might mean the
requirements themselves are still moving. Genuinely not sure which yet.

Going to stop rewriting and go ask the three people actually using it
instead.

When do you stop iterating alone and go get more input?

*Score emphasis:* `voice_authenticity` 9 (admits the loop instead of hiding
it), `hook` 7, `cta` 8.

---

## CATEGORY: industry_opinion

### Example 1 (observation-led)

Watched three different teams roll out the same AI coding tool this
quarter. Same tool, wildly different outcomes.

The two teams that saw real gains didn't have more AI usage. They had more
precise problem statements before they ever opened the tool.

The team that saw nothing measurable just asked vaguer questions, faster.

AI didn't fix a documentation and clarity problem. It just made the cost of
skipping that step temporarily invisible.

Where's the gap on your team -- output, or precision?

*Score emphasis:* `topic_resonance` 9, `profile_fit` 7, `hook` 8.

### Example 2 (contrarian-claim)

"Ship fast and break things" was never actually good advice for most teams.
It was good advice for one company, at one specific stage, that everyone
else copied without the context.

Most teams I've worked with broke more trust than they gained speed.

The version that's actually served me well: ship fast on things that are
cheap to undo, go slower on things that aren't.

Where do you draw that line on your team?

*Score emphasis:* `hook` 9 (challenges an industry cliche directly),
`profile_fit` 8, `voice_authenticity` 8.

### Example 3 (number-led)

Two candidates, same experience level, same take-home test score. One got
the offer.

The difference wasn't skill -- it was that one of them asked three
clarifying questions about the actual problem before writing a line, and
the other jumped straight to code.

I've started weighting that more than the code itself in interviews.

What's the signal you've started trusting more than the obvious one?

*Score emphasis:* `hook` 8, `profile_fit` 8, `topic_resonance` 8.

### Example 4 (flat-statement)

Remote work didn't kill mentorship. Badly designed remote onboarding did.

The teams I've seen keep strong mentorship remote were deliberate about it
-- scheduled pairing, recorded walkthroughs, explicit norms about asking
"obvious" questions in public channels.

The teams that lost it just assumed presence would happen on its own, the
way it used to in an office. It doesn't, remotely, by default.

What did your team have to make deliberate that used to just happen?

*Score emphasis:* `hook` 8 (reassigns blame from the trend to the
execution), `topic_resonance` 8, `profile_fit` 7.

### Example 5 (scene-led)

Sat in a hiring debrief where someone said "they didn't get the optimal
solution" about a candidate who'd given a working, well-reasoned, slightly
slower answer.

We hired someone else. I still think about whether that was the right
call.

Optimal-on-a-whiteboard and effective-on-a-team aren't the same skill, and
I'm not sure our interview process actually tests the second one.

Has your interview process ever told you the wrong thing about someone?

*Score emphasis:* `voice_authenticity` 9 (admits ongoing doubt instead of a
tidy conclusion), `hook` 8, `topic_resonance` 8.
