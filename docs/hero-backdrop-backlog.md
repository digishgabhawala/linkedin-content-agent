# Hero and recurring-backdrop backlog

This backlog keeps follow-up ideas from expanding the current vertical
slice. Items move into implementation one at a time, each with its own
branch, tests and review.

## Current slice

- [x] Let Character Forge accept explicit hero/card/output paths while
  preserving its local workspace defaults.
- [x] Store the complete CharacterCard, content-addressed hero asset id and
  hero version with the synced remote character.
- [x] Send that locked-character snapshot with post-image tasks.
- [x] Let workers download/cache the remote hero and render without a local
  `workspace/<character>/hero.png`.
- [x] Add a stateless Character Forge command and
  `hero_candidate_generation` worker contract for one candidate per queue
  task, with artifact and generation metadata returned on completion.
- [x] Add generation-run and hero-candidate tables, submit one task per
  candidate, and promote completed queue artifacts into durable Storage.
- [x] Add authenticated Character Studio APIs for create, generation status,
  candidate review and transactional hero locking.
- [x] Add the responsive Character Studio UI for character-card creation,
  queue-aware candidate generation, review and hero locking.

## Next product slices

- [ ] Scope characters, posts and recurring backdrops by authenticated owner.
- [ ] Add CharacterCard editing with explicit version history; today a card
  is immutable after creation and locking preserves its generation snapshot.
- [ ] Add an explicit retry action for an individual failed hero candidate;
  today recovery is a new candidate run so failure history stays visible.
- [ ] Add archive/delete management for unused characters and generation
  runs after real usage clarifies safe retention rules.
- [ ] Version backdrop descriptions so an old post can remain reproducible
  while still offering an explicit "use latest backdrop" action.
- [ ] Evaluate reference-image-backed recurring environments after the
  current text-backed backdrop system has enough real usage data.

## End-of-initiative hardening

- [ ] Move character images from public URLs to private objects with short
  signed URLs when multi-user access is enabled.
- [ ] Define hero-cache size limits, eviction and integrity verification.
- [ ] Add per-asset cache locking if a worker later processes concurrent
  tasks; today's worker intentionally runs one task at a time.
- [ ] Restrict worker downloads to trusted Storage origins before arbitrary
  third-party producers can submit tasks.
- [ ] Decide archival/cleanup rules for superseded hero versions and post
  renders.
