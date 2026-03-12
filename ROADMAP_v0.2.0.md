# PO Builder v0.2.0 Roadmap

Status: proposed

Current version: `0.1.7`

Target release: `0.2.0`

## Why v0.2.0

The recent `0.1.x` releases have mostly focused on reliability, shared-data behavior, and refactoring core workflows out of the main app controller.

`v0.2.0` should mark the point where PO Builder is considered stable enough for routine shared-folder use and easier to maintain without making every change inside `po_builder.py`.

This is not just "the next release after `0.1.7`". It is a milestone release with explicit release gates.

## Release Theme

`v0.2.0` = workflow stability + maintainability

That means:

- the main ordering workflow should be predictable with normal X4 inputs
- shared/local data behavior should be understandable and safe for day-to-day use
- the app should have stronger regression coverage around the workflows that matter most
- the main controller should continue shrinking as feature logic moves into focused modules

## In Scope

The `v0.2.0` milestone should prioritize these four areas.

### 1. Shared-data hardening

Goal: make local/shared folder usage safe enough that it no longer feels experimental.

Complete this area when:

- refresh behavior is consistent across rules, vendors, ignore list, history, and related saved state
- shared-folder writes are still atomic and lock-protected
- concurrency-sensitive files are either hardened further or clearly constrained in the UI/help text
- error handling explains what happened when shared data cannot be loaded or saved

Suggested work:

- review the current handling of `suspense_carry.json` and decide whether to merge, lock longer, or reduce write frequency
- add regression tests for active-folder refresh during a live session
- verify that local-to-shared and shared-to-local switching does not leave stale state in memory

### 2. Main-controller decomposition

Goal: reduce the maintenance risk still concentrated in `po_builder.py`.

Complete this area when:

- workflow logic continues moving into focused modules instead of staying in the main window/controller
- UI event handlers stay thin and delegate to testable helpers where practical
- newly added behavior is not implemented by further growing `po_builder.py`

Suggested work:

- identify the next highest-churn sections still living in `po_builder.py`
- extract them behind module-level helpers similar to `assignment_flow.py`, `load_flow.py`, `item_workflow.py`, `export_flow.py`, and `maintenance_flow.py`
- add tests alongside each extraction so the refactor is not only structural

### 3. Workflow-level regression coverage

Goal: treat the full ordering workflow as a product surface, not just a set of helpers.

Complete this area when:

- the expected happy path is covered from load through export
- the most common failure and recovery paths have tests
- version/update behavior and release-sensitive paths remain covered

Suggested work:

- add end-to-end style tests for load -> assign -> review -> export
- add tests for ignored items, shared-data refresh, and missing/blank inventory values in the same workflow
- verify the built app still behaves correctly when optional assets are absent

### 4. Release discipline

Goal: make releases easier to cut and safer to trust.

Complete this area when:

- release notes follow one consistent format
- the release checklist is documented and repeatable
- the version bump, tests, and build verification steps are always performed the same way

Suggested work:

- standardize the top-level release note structure used by `RELEASE_v*.md`
- add a repeatable release checklist for version bump, tests, build, smoke test, tag, and GitHub release
- keep `VERSION` as the single source of truth for the app version used by the startup update check

## Not In Scope

These items should not block `v0.2.0` unless they directly affect stability.

- large UI redesigns
- speculative new ordering features without a clear user problem behind them
- broad dependency churn without a direct release need
- major platform expansion beyond the current Windows desktop workflow

## Release Gates

Do not cut `v0.2.0` until all of these are true.

### Gate 1. Stable shared-data behavior

- shared/local switching works without stale or misleading UI state
- refresh-from-disk behavior is verified
- known concurrency-sensitive files have either improved handling or explicit documented limits

### Gate 2. Refactor momentum continues

- at least one additional high-risk slice of `po_builder.py` has been extracted cleanly
- the extraction includes unit tests or workflow tests

### Gate 3. Workflow confidence

- the full unit test suite passes
- at least one real built-exe smoke test has been performed against representative X4 exports
- export output remains correct for at least one multi-vendor scenario

### Gate 4. Release process is documented

- release notes are written
- the release checklist is followed
- `VERSION` and Git tag match the intended release

## Recommended Path From 0.1.7

### Phase 1. Finish patch-level reliability work

Continue shipping `0.1.x` only for narrowly scoped fixes:

- regressions found in bulk assignment
- shared-folder save/load issues
- parser tolerance issues from real X4 files
- export correctness bugs

Do not expand feature scope here.

### Phase 2. Create an internal release candidate

Once the next refactor and shared-data hardening pass are in place:

- bump to an internal `0.2.0-rc` build or equivalent milestone tag if useful
- run a real workflow smoke test on the packaged `.exe`
- verify local-data and shared-data scenarios separately

### Phase 3. Cut v0.2.0

Ship `v0.2.0` only after the release gates are satisfied and the packaged app has been tested in the same way users run it.

## Concrete Backlog For v0.2.0

Shortlist the next work under this milestone:

1. Harden `Refresh Active Data` and shared/local switching with regression tests.
2. Reduce the highest-risk remaining workflow block inside `po_builder.py`.
3. Add workflow-oriented tests that cover export correctness after assignment changes and ignored-item handling.
4. Add a release checklist document and use it for the next release candidate.
5. Smoke-test the built executable with representative real-world CSV inputs before tagging `v0.2.0`.

## Definition Of Done

`v0.2.0` is done when the app is no longer mainly proving out reliability fixes from release to release, and instead has:

- stable shared-data behavior
- better-structured workflow code
- strong regression coverage for the main user flow
- a repeatable release process
