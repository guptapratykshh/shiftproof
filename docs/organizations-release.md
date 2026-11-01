# Organization accounts and the 3D landing page

Implemented October 16, 2026 (IST). React, FastAPI and SQLite remain local. AWS and billing settings were not changed.

## Open the application

- Landing page: http://localhost:5173/
- Create an organization: http://localhost:5173/signup
- Sign in: http://localhost:5173/login
- Interactive fictional factory: http://localhost:5173/demo
- Temporary public site: read `.local/current-public-url.txt` for the current tunnel URL.

The public server is port 8080; its tunnel requires this Mac, the server and cloudflared to remain running. Private localhost accounts and public-preview accounts are intentionally separate. The current temporary URL is also stored in ignored `.local/current-public-url.txt`.

## Delivered behavior

The landing page retains the green, cream and orange identity. A lazy-loaded Three.js illustration changes between eight industry settings. Industry selection is keyboard accessible. Reduced motion, offscreen/tab suspension and a WebGL fallback are implemented. The page includes an illustrative handover, an evidence trail and the historical manufacturing benchmark with its limitations; it makes no customer or cross-industry accuracy claims.

Separate signup and sign-in pages create real accounts. Signup now shows exactly name, email, password, confirm password and organization type. Password visibility, confirmation and a local strength estimate are included; the backend retains its 12–128-character rule. Timezone is detected from the browser with an Asia/Kolkata fallback. New workspaces are empty and initially named “[Name]’s workspace.” Owners edit the workspace name in Settings > General; timezone is under Advanced settings. Settings separates locations/teams, dated shifts, recording policy and downloads. New owners receive a resumable five-step setup. Dated shift occurrences have explicit assignments and scoped handovers; recurring scheduling remains deferred. See [portal verification](pilot-ui-checklist.md) for the current interface and test evidence.

| Organization type | Status | Operational model |
|---|---|---|
| Manufacturing | Working | Batches, quantities, packing, quality, dispatch and tasks |
| Equipment maintenance | Working | Assets, operating status, unresolved faults, temporary/permanent repair and tasks |
| Warehousing | Working | Orders, quantities, packing, document verification, dispatch and tasks |
| Quality assurance | Preview as a standalone organization | Quality reviewers remain available within manufacturing |
| Food processing | Preview | Organization setup and team invitations only |
| Construction | Preview | Organization setup and team invitations only |
| Healthcare | Preview | No clinical capture, patient records or clinical validation |
| Facility management | Preview | Organization setup and team invitations only |

Preview organizations cannot create operational items or notes. Working profiles have distinct extraction constraints, readiness prerequisites and clarification questions. A running machine cannot clear a fault. Packing cannot verify warehouse documents. Inspection task completion cannot clear a manufacturing quality hold. Clearance requires the authorized reviewer role.

The workspace supports voice recording, transcript inspection, extraction, manual interpretation, source playback, corrections, explicit supersession, tasks, clarification, evidence-linked questions and versioned acknowledgement. Original recording times and transcript revisions remain visible. Reviewer retries preserve the original speaker and reuse saved transcription. Failed extraction never substitutes a fixture. The new industry prompts have separate fingerprints from the historical manufacturing prompt.

## Accounts, permissions and storage

Passwords use Argon2. Sessions are stored server-side and use HttpOnly/SameSite cookies, Secure over the public HTTPS host. Authenticated changes require a CSRF token; account mutations also reject untrusted browser origins. Password change, logout, expiry and recovery revoke the appropriate sessions. Five one-time recovery codes are displayed once at signup. No email is sent or claimed verified; social login and email recovery are deferred.

Owners manage membership. Administrators can invite members; members cannot invite or elevate privileges. Owner/admin/member access is separate from operator/supervisor/authorized-reviewer permissions. Initial organization owners are supervisors, not automatic clearance reviewers. An owner can explicitly assign operational reviewer permission. The last owner cannot be removed or demoted. Invitations are bound to the account email, expire after 72 hours and can be accepted once. These links must be shared manually.

The interface labels the creator **Organization owner** and the operational `operator` role **Shift worker**. Add team member takes a name, email and assigned role. The person activates their account and chooses their own password, or signs in to their existing account. Pending, accepted, expired and revoked invitations are visible to owners/administrators. Replacing a pending or expired link atomically revokes the previous link; accepted invitations are managed through membership instead. Access history records who created, replaced, revoked or accepted an invitation and who changed or removed membership. Pre-upgrade actions are not retroactively invented. Raw invitation tokens are never returned in invitation listings or audit history.

Every organization operation resolves authenticated membership before loading its SQLite repository or audio directory. Jobs receive the repository explicitly; no process-global workspace switch is used. Full navigation between organizations discards in-memory caches and warns about an unfinished capture. Changing an organization's industry is not exposed; create a separate organization for a different workflow.

- Identity database: `.local/accounts/identity.sqlite3`.
- Organization records and recordings: `.local/accounts/organizations/<id>/`.
- Fictional local demo: `.local/demo/`.
- Public accounts: `.local/public-preview/accounts/`.
- Fictional public demo: `.local/public-preview/demo/`.
- Shared provider-attempt budget: `.local/shared-usage.sqlite3`, overridable with `SHIFTPROOF_SHARED_USAGE_DB`.

Existing public-demo records were copied to the new demo location without changing their original database. The old private database and recordings remain preserved and were backed up before restart. Public signup never adopts them.

### Explicitly import your previous private workspace

Create your own localhost account first. Then run this command locally, substituting that account's email:

```sh
PYTHONPATH=backend .venv/bin/python scripts/adopt_legacy_workspace.py \
  --owner-email 'your-account@example.com' \
  --organization-name 'My existing manufacturing workspace'
```

The importer requires an existing account, creates a separate manufacturing organization, backs up the original database/audio, preserves claims, reviews and acknowledgement snapshots, and records an idempotent ownership receipt. Rerunning it returns the same organization. Original files are not modified. This is deliberately not a public API. No account was chosen on the user's behalf during this delivery.

Provider quotas count attempted model/speech calls globally across this installation, with an additional per-organization limit (default 50 each per UTC day). They do not independently verify provider billing status. Provider scripts/evaluations retain their explicit run budgets; the installation ledger covers application processing. Free-tier Gemini remains pinned to `gemini-3.5-flash-lite`; Prisma and Timbre stay backend-only integrations.

## API additions

- `/industries`: versioned profiles and availability.
- `/auth/signup`, `/auth/login`, `/auth/session`, `/auth/logout`, `/auth/password`, `/auth/recover`: account lifecycle.
- `/organizations`, `/organizations/{id}`, `/organizations/{id}/setup`: organization creation and setup.
- Organization membership and invitation routes; `/invitations/{token}` and `/invitations/accept`.
- `/organizations/{id}/work-items`: create work items; update metadata with the expected workspace version.
- Organization-scoped equivalents of notes, audio, processing, revisions, manual interpretation, claim review, questions, tasks, speech, handover, snapshots and acknowledgement.
- `/organizations/{id}/export`: authenticated record export.

Team-management update: `PUT /organizations/{id}/settings` changes name/timezone for owners only; `GET /organizations/{id}/invitations` lists invitation statuses; `DELETE /organizations/{id}/invitations/{invitationId}` cancels a link; `POST /organizations/{id}/invitations/{invitationId}/replace` returns a replacement link; `GET /organizations/{id}/access-events` returns recorded account-administration events. Signup accepts omitted organization names and optional `confirm_password` for compatibility with existing clients; the browser requires matching confirmation. Invitations accept an optional name for compatibility with previously issued invitations.

Legacy unscoped endpoints and demo bearer tokens refer only to fictional demo records. The response fields used by the existing demonstration remain compatible. Arbitrary organization work-item identifiers replace the former six-ID restriction; unsupported identifiers still fail organization membership/work-item validation.

## Validation and evidence

**Latest team-management verification: 182 backend tests and 19 browser tests passed; the production build passed.** The previous organization release had 176 backend and 17 browser tests. See `artifacts/team-release-validation.json`, `artifacts/team-backend-tests.xml` and `artifacts/team-browser-tests.json` for the latest machine-readable results. Regression coverage includes cross-organization reads/writes/audio/export, demo-to-private denial, invitation expiry/reuse/revocation/replacement, membership revocation, password recovery, CSRF, last-owner protection, hold persistence, industry validation, stale resolutions/clarifications, duplicate processing and preserved acknowledgement snapshots. The original six live industry development checks were not rerun for this account/UI update.

The six live development text checks passed: two manufacturing, two maintenance and two warehouse examples. They used real signup, create-note and processing services in isolated temporary databases, with live Gemini and no fixture fallback. Results, expected/actual claims, timings and prompt/model provenance are in `evaluation/results/industry-development-smoke.json`. This is a small development integration check, not independent industry accuracy or a new held-out benchmark.

Browser evidence:

- [Simplified mobile signup](../artifacts/team-signup-mobile.png)
- [Named invitations and access history](../artifacts/team-management.png)

- [Desktop landing page](../artifacts/organizations-landing-desktop.png)
- [Mobile landing page](../artifacts/organizations-landing-mobile.png)
- [Signup](../artifacts/organizations-signup.png)
- [Private organization workspace](../artifacts/organizations-private-workspace.png)
- `artifacts/organization-browser-check.json`: real WebGL rendering, no browser errors and no mobile overflow.
- `artifacts/organization-public-check.json`: public signup, empty private workspace, authenticated write, Secure/HttpOnly cookie and demo access denial.

The voice browser checks use a fake microphone and an explicitly mocked transcription checkpoint. They verify browser WAV upload, transcript inspection and reuse of the same note; they are not new human recordings. The prior live Gnani demonstration and manufacturing benchmark remain separately disclosed in `docs/re-rating-report.md`. Independent annotations, real factory usefulness, new industry benchmarks and clinical validation remain unmeasured.

## Reproduce and walkthrough

```sh
.venv/bin/pip install -e './backend[dev]'
npm ci --prefix frontend
.venv/bin/pytest backend/tests -q
npm run build --prefix frontend
npm run test:e2e --prefix frontend
PYTHONPATH=backend .venv/bin/python scripts/check_industry_profiles.py
```

The final command makes live Gemini requests using the existing free-tier configuration. It writes only development-check results, never a held-out score. Use the existing startup commands in README for ports 8000/5173, and `scripts/public_preview.py` for the isolated public instance.

Walkthrough: explore the eight landing-page settings → create a manufacturing/maintenance/warehouse organization → save recovery codes → configure the team → add a work item → record or type a report → inspect the transcript → extract/review evidence → answer a clarification → acknowledge the handover version. Invite a second account as an authorized reviewer to test clearance and membership boundaries.

Known operational limits: local SQLite and temporary hosting, manually shared invitations, recovery codes instead of email recovery, one current handover per organization, no automated data-retention/deletion policy, and five preview industries. The lazy-loaded Three.js bundle produces Vite's >500 kB chunk advisory; it is separated from the primary application bundle. No AWS deployment, email outreach or competition submission was performed.

## Team-management walkthrough and feature parity

1. Open `/signup`. Enter the five visible fields, save recovery codes, and open the empty workspace. The creator is labeled Organization owner and starts with Shift supervisor permissions.
2. In Settings, rename the workspace if desired. Timezone is optional setup, and timestamps use that organization timezone. Locations/teams/shifts remain organizational labels.
3. In People & access, add a named Shift worker, Shift supervisor or Authorized reviewer. Share the activation link yourself. A new person sets their own password; an existing account signs in and accepts. Neither person selects their privileges.
4. Inspect pending invitations, replace a link, and verify the earlier link no longer works. Cancel another invitation and open Access history. Changes are scoped to this organization.
5. Add a batch, asset or order. Record or type an update, inspect the transcript, and submit it. Failed extraction retains the transcript for retry or reviewer interpretation.
6. Open Evidence & history to inspect transcript revisions, human interpretations, claim status, review reasons and correction targets. The author can correct a saved transcript. This creates a new revision; earlier claims and reviews stay active until explicitly rejected or superseded. A failed new revision can be manually interpreted even when an older revision already has claims.
7. Review the outstanding work and acknowledge its exact handover version. A subsequent material revision makes the acknowledgement stale while its stored snapshot remains accessible.
8. Use Settings → Download organization data. The JSON includes workspace records and evidence references. It does not bundle audio recordings; playback remains authenticated.

| Capability from the demo | Organization workspace verification |
|---|---|
| Record WAV, inspect transcript, then extract | Browser test with fake microphone and mocked Prisma checkpoint; saved note reused |
| Failed extraction and human interpretation | Browser checks for manufacturing, maintenance and warehousing |
| Original reports, transcript versions and human decisions | Evidence dialog includes note-linked interpretation events and claim-linked review events |
| Correct a saved transcript without losing earlier reviews | Browser manufacturing check plus backend revision/recovery and snapshot regression |
| Explicit quality/fault/document hold clearance | Backend role checks across all three working profiles; owners do not automatically receive clearance |
| Tasks, pending/hold/history questions, clarification and acknowledgement | Existing core and browser regressions retained; three-profile handovers tested |
| Data export | Visible download action; browser verifies claims and acknowledgements in each profile's JSON |
| Role switching | Demo retains fictional persona switching; private organizations use authenticated, owner-assigned memberships |
| Manufacturing benchmark | Historical results remain on the landing page/demo; no private-organization accuracy score is fabricated |
| Multiple concurrent shifts or five preview workflows | Not implemented; disclosed in Settings and preview pages |

The strength meter is a local heuristic, not a password breach check or a guarantee. Browser/API checks use isolated fictional data and controlled providers; they are not new live-Gemini accuracy measurements or human-audio study results. Existing local/private and public operational databases were backed up before restart, with no destructive workspace migration.
