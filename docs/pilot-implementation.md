# Manufacturing pilot implementation report

Updated 16 October 2026. This release implements the software foundation for one factory pilot. **It is not yet approved for real factory data or production deployment.** Existing manufacturing model results are separate from the engineering checks below; maintenance and warehousing remain demonstrations and five industries remain previews.

## Issue register

| Previously reproduced issue | Implemented change | Evidence / remaining boundary |
|---|---|---|
| Recording can move to another work item | Frozen account, organization, item, shift and clarification context; navigation guards; locally persisted drafts | Browser recording/navigation/reload checks; real phone interruptions still require observation |
| Independent tasks conflict | Independent task identity, named membership assignments, report-done then verify | Backend regression checks; inspection completion cannot clear a hold |
| Revised transcript leaves old completion active | Original interpretation retained with reconciliation required; readiness blocks until review | Source-revision tests |
| Removed worker's unfinished upload blocks handover | Audited takeover, cancellation or carry-forward; supervised import of captures over 72 hours late | Recovery tests preserve original author, recording time and immutable audio |
| Restart leaves jobs stuck | Separate durable worker, expiring leases, fencing, persisted transcription and bounded network attempts | Controlled restart/lease tests; actual-host restart drill remains required |
| Workers can export or browse unrelated records | Owner-only export; current membership and dated assignment checks on records, files, jobs and snapshots | Cross-organization and cross-scope API tests |
| Shared shift identifier | Dated occurrences, teams, locations, recipients, incoming supervisors and immutable closed snapshots | Shift and overnight tests; unassigned legacy history remains an archive |
| Refresh loses work | IndexedDB drafts and explicit send queue, periodic recording checkpoints | Abrupt termination may lose the final checkpoint interval; device/browser data deletion is not recoverable |
| Stale permission and workspace views | Scoped refresh on polling, reconnect and foreground; authorization checked again at upload and provider execution | Backend and browser checks; offline drafts grant no server access |
| Reads rewrite growing JSON | Indexed SQLite records, read-only queries, scoped mutation and paginated notes | Migration/read-preservation tests and measured load probe |
| Removed member gets login dead end | Signed-in no-access state and organization-specific employee activation/login | Account and browser regressions |
| Unchanged reviews invalidate receipt | Idempotent review and duplicate processing; material per-shift versions | Acknowledgement tests; other changes in the same shift can still require a new receipt |
| Delegated administrator can appoint reviewers | Central role rules; owner appoints supervisors/reviewers | Permission-tampering and invitation tests |
| Overcomplicated private UI | Demo visual language, Hindi worker destinations, role-specific controls and evidence details | Screenshots and browser checks; worker usability study pending |
| No-email workers | Organization-scoped employee IDs, activation links and reset flow | Scoped credential/reuse/removal tests; owner and supervisor email accounts retained |
| Overlapping audio and typed-only receipt | Controlled playback, stop-before-record, spoken receipt with explicit confirmation | Browser checks use simulated microphone input |
| Storage exhaustion loses context | Upload quotas/free-space checks, recoverable errors, temporary-file cleanup | Disk-full/retry regression; server never substitutes invented content |
| Temporary hosting and missing recovery procedures | Persistent-host container/worker/proxy package, health command, encrypted backup/restore and rollback runbook | Local restore passed; container and actual-host validation pending |
| Confidential data sent through free AI configuration | Explicit capture policy on pilot host, separate approved business configuration and budgets | Provider gate tests; terms approval is an external release gate |

Spoken acknowledgement drafts use a separate account/organization/shift store and retain the captured version across refresh. Password changes preserve unsent drafts; signout explicitly warns before removing account drafts across organizations. Handover fingerprints use canonical ordering so database row order alone cannot invalidate a receipt.

The full permission contract is in [pilot-permissions.md](pilot-permissions.md). Account ownership alone does not authorize hold clearance. Supervisors coordinate their assigned scope; workers record, report assigned work done and acknowledge their handover. Authorized reviewers resolve protected holds with evidence and a reason.

## Interface comparison

The [original demo](../artifacts/overview.png) is the visual reference: dark green navigation, cream canvas, restrained orange actions and compact evidence cards. The [private supervisor view](../artifacts/pilot-supervisor-overview.png) and [Hindi worker mobile view](../artifacts/pilot-worker-hindi-mobile.png) use the same visual language. Workers receive record, assigned work and handover destinations; people, exports and settings belong to owner administration.

## Fictional pilot walkthrough

1. Sign up as the organization owner. Save recovery codes, then open Settings and select fictional practice data. Create the location, team, carton work item and dated shifts in the organization's timezone.
2. Add a worker using an employee ID and a supervisor using email. Share their activation links manually. Assign them to the appropriate shift/work items and designate the incoming supervisor. Explicitly appoint a reviewer for protected holds.
3. As the worker, record a packing update in Hindi, inspect the transcript and send it. Capture another update offline, reload and reconnect; inspect the saved draft before explicitly sending. Provider failures keep the completed evidence available for recovery or manual interpretation.
4. As the supervisor, review packing, quantity and independent tasks. Report a seal-inspection problem and leave its quality hold open. A later packing-complete or dispatch-ready report must still show the hold. An assigned worker can report an inspection task done; verifying that task does not clear the hold.
5. As the authorized reviewer, inspect the sources and resolve the hold with evidence and a reason. As an assigned incoming participant, listen to outstanding work and confirm the displayed handover version. A subsequent material update requires a new receipt; the earlier snapshot remains unchanged.
6. As owner, download the organization's data. Exercise failed-job recovery with a recorded reason and verify that original authorship and audio remain intact. Workers cannot use the export or people-management endpoints.

Use the labeled scripted samples or explicit manual interpretation without provider credentials. Arbitrary speech needs Prisma and automatic language extraction needs a working Gemini configuration; fixtures must not be presented as live inference.

## Data preservation and measured checks

Before local migration, application writers were stopped and **17 files** were encrypted and restored into an isolated directory. Migration preserved existing notes, claims and snapshots across **five workspace databases**. The subsequent live comparison preserved pre-existing records across **seven identity/workspace databases**. See [backup evidence](../artifacts/pilot-backup-migration.json) and [migration comparison](../artifacts/pilot-live-migration-check.json). Backups and encryption keys are private and excluded from the repository.

The current complete backend run passed **256 tests**, with two dependency deprecation warnings: [JUnit results](../artifacts/pilot-backend-tests.xml). This includes simulated backup-scheduler success, preflight failure and backup failure, verifying writer restart without pretending to run Docker. The Python dependency audit found **zero known vulnerabilities across 41 pinned dependencies**; the frontend audit also found zero. These are dated audit results, not guarantees of security.

The [browser suite](../artifacts/pilot-browser-tests.json) passed **29/29**, with no skips or flaky results. The separate [production service-worker test](../artifacts/pilot-offline-browser-tests.json) passed **1/1**: offline reload, local microphone capture, reconnect/session verification, retained draft and no automatic submission or private API cache. These tests use simulated microphone input. The [production build](../artifacts/pilot-frontend-build.log) passed; its separately loaded 3D chunk still produces Vite's size advisory.

The [load probe](../artifacts/pilot-load-probe.json) used 50 registered workers plus an owner, 10 concurrent clients and 10,000 historical notes, with corresponding claims and reviews. **80/80 operations completed**, with no observed scope or lock errors. Authenticated workspace-read p95 was **1.67 seconds**; note-creation p95 was **4.52 seconds**. Write latency remains a bottleneck. This short local run excludes provider calls, sustained processing traffic and real internet/device latency. See [core verification](core-pilot-verification.md) for denominators and the retained earlier failure artifact.

## Reproduction

From the repository root:

```sh
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q --junitxml=artifacts/pilot-backend-tests.xml
PYTHONPATH=backend .venv/bin/python scripts/pilot_load_probe.py --workers 50 --history-notes 10000 --concurrency 10
```

From `frontend`:

```sh
npm ci
npm run build
npx playwright test
npx playwright test --config playwright.offline.config.ts
npm audit
```

For local use, `scripts/dev.sh` starts the frontend, API and processing worker. Follow [pilot-runbook.md](pilot-runbook.md) for persistent-host deployment, policy setup, recovery and encrypted backup commands.

## Remaining release gates

- Run the container build, Compose validation, HTTPS/cookie/proxy checks, sustained load, monitoring, restart and restore drills on the intended persistent host. This machine has neither a running Docker daemon nor the Compose plugin; [deployment checks](../artifacts/pilot-deployment-check.json) explicitly record these as not run.
- Resolve provider processing terms, separate approved business credentials, factory consent, retention/deletion policy and spending limits before collecting or processing real recordings. AWS and billing were not enabled.
- Observe five intended workers and two supervisors on their personal phones using [the usability protocol](pilot-usability.md). Browser simulations do not establish comprehension, audio quality or storage durability on those devices.
- Accept or improve the measured write latency. Current compatibility mutations still reconcile the selected item's history; SQLite serializes writes. Do not claim this establishes sustained production capacity.
- Retention tooling currently inventories records due for review. An approved deletion procedure and backup-expiry policy remain necessary; no evidence was silently deleted.

No new live-model accuracy, independent participant evaluation or industry-readiness result is claimed by this implementation.
