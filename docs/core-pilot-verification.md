# Core pilot verification

Verified on 16 October 2026 for the bounded, single-host manufacturing pilot. These checks establish software behavior under controlled inputs. They do not establish live speech accuracy, factory usability, production capacity or compliance with a provider's terms.

## What changed

- SQLite stores notes, claims, decisions, jobs and other collections as indexed records. Reads do not rewrite the workspace. Diff writes preserve untouched rows; the original workspace JSON remains an immutable migration archive. Back up the database and recording directory before applying the additive migration to another installation.
- Work-item-scoped transactions reject cross-item source changes and collisions with unloaded record IDs. Exact-ID reads used for idempotency do not grant write access. Transaction scope markers cannot be supplied or changed by callers and are never persisted.
- Per-item material fingerprints preserve unrelated handover versions. Migrated shift workspaces with missing fingerprints initialize them once from complete history. Subsequent scoped changes preserve unloaded evidence and fingerprints. The cache is not an authorization boundary: API membership, assignment and response filtering remain required.
- Persistent processing jobs survive a lost worker lease, retain completed transcription and record network attempts before requests. Enqueue, retry, execution and provider attempts recheck membership and scope. Late results cannot overwrite a replacement lease. An explicit retry preserves previous attempt history.
- Independent tasks can be reviewed separately. Assigned workers report completion; supervisors verify it. Transcript revisions retain earlier claims but block readiness until those interpretations receive explicit review. Repeated unchanged decisions do not invalidate acknowledgements.
- A partial-quantity exception applies only to its recorded dispatch requirement and accepted reviewed count. A changed requirement, a corrected lower count, unknown quantity or an old unbound exception requires another supervisor review.
- Real-data inference requires explicit organization declarations and separately configured business-provider credentials. It does not fall back to the free Gemini key. The pilot host can require an explicit data policy before capture; `SHIFTPROOF_REQUIRE_DATA_POLICY=true` enforces that boundary. Provider configuration records a review decision, not a legal determination. Demo and private usage have separate pools beneath a shared ceiling.

## Reproduce the checks

Run from the repository root with the existing virtual environment:

```sh
PYTHONPATH=backend .venv/bin/pytest -q backend/tests --junitxml=artifacts/pilot-core-full-backend-tests.xml
PYTHONPATH=backend .venv/bin/pytest -q backend/tests/test_pilot_core_storage_jobs.py
PYTHONPATH=backend .venv/bin/python scripts/pilot_load_probe.py --workers 50 --history-notes 10000 --concurrency 10
```

The core checkpoint passed **245 backend tests**, with two dependency deprecation warnings, in 10.23 seconds. The focused core file contains **22 passing tests**, covering migration/read preservation, partial-write isolation, missing-cache initialization, source revisions, task completion, quantity exceptions, duplicate actions, durable jobs, lease fencing, authorization and provider gates. That checkpoint is retained in [pilot-core-full-backend-tests.xml](../artifacts/pilot-core-full-backend-tests.xml). The subsequent complete release check passed **256 tests**, including storage limits and scheduled-backup failure handling: [current backend results](../artifacts/pilot-backend-tests.xml).

The load probe creates and deletes temporary identity and organization databases. It neither uses existing private records nor calls speech or extraction providers. It uses real authenticated API workspace reads and note-creation requests, plus indexed repository reads. Sessions and historical records are controlled fixtures; account activation is covered separately by backend/browser tests.

## Measured local envelope

The [latest probe](../artifacts/pilot-load-probe.json) used **50 registered workers plus one owner (51 identities)**, 10 concurrent clients, 10 work items, and 10,000 historical notes with corresponding claims and review events. Each work item held 1,000 historical notes. Runtime: Python 3.12.12, SQLite 3.50.4, macOS, DELETE journaling.

| Operation | Samples | p50 | p95 | Errors |
|---|---:|---:|---:|---:|
| Authenticated workspace read | 30 | 272 ms | 1,667 ms | 0 |
| Configuration/index read | 10 | 148 ms | 389 ms | 0 |
| Indexed scoped page | 20 | 64 ms | 238 ms | 0 |
| Authenticated note creation | 20 | 1,260 ms | 4,519 ms | 0 |

All **80 operations completed**, with zero observed lock failures or scope violations and zero provider calls. Percentiles use nearest rank and include all attempted operations. This is one short local run with 10 active clients, not 50 simultaneously active workers. It excludes audio uploads, internet latency, provider calls, browser rendering and sustained background-worker traffic.

The earlier [pre-optimization artifact](../artifacts/pilot-load-probe-before-write-optimization.json) retains 11 failed note writes. Its opaque HTTP 500 responses prevent reliable attribution to lock contention; that diagnosis is explicitly unknown. Its fixture had 49 workers plus one owner, so it is historical troubleshooting evidence rather than a matched performance comparison.

## Remaining limits

Write p95 remains about **4.5 seconds** in this burst. SQLite serializes writers, and compatibility transactions still load and reconcile the selected item's history. A busy item with much more history, sustained worker traffic or slower disks can exceed this envelope. The next scaling work is to reduce history read during mutation, then repeat sustained tests on the actual host; PostgreSQL remains an option if measured concurrency requires it.

The current runtime stays in DELETE mode. WAL is rejected on unpatched runtimes; SQLite documents the WAL-reset fix in 3.51.3 and the 3.50.7/3.44.6 backports. See [SQLite's WAL-reset guidance](https://www.sqlite.org/wal.html#the_wal_reset_bug). Enabling WAL requires an approved patched runtime and another verification run.

Job recovery tests use controlled crashes and provider doubles. They verify application state and request bounds, not exactly-once external billing after an ambiguous network failure. The durable worker still requires process supervision and health monitoring on the persistent host.

Live business-provider approval, factory consent, retention decisions, real-device offline checks and practitioner evaluation remain separate release gates. A production-browser regression now verifies reopening offline from a cached public shell and a minimal, 72-hour last-signed-in capture context. Offline mode exposes recording and local drafts only; assignments are explicitly unverified. Reconnection requires a fresh authenticated session before restoring and explicitly sending a draft. Private API responses and audio are never placed in service-worker Cache Storage. Active recording checkpoints save approximately once per second; abrupt closure can lose the final second. Real-device checks remain pending. Manufacturing benchmark evidence does not establish accuracy for other industries.
