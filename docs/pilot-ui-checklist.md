# Pilot interface verification

The private workspace now uses the original demo palette and shared sidebar/navigation primitives. The original `/demo` remains a separate, fictional interactive workspace. This release supports a bounded manufacturing pilot; browser checks do not establish worker comprehension or production capacity.

## Role journeys

| Account | Visible operational destinations | Administration | Protected decisions |
|---|---|---|---|
| Shift worker | Record, My work, Handover; Hindi by default with an English switch | Personal account only | Reports assigned task completion; cannot review reports or clear holds |
| Shift supervisor | Overview, Voice & reports, Handover | Own personal account; assigned work-item coordination | Ordinary review, named task assignment and verification; cannot clear protected holds |
| Authorized reviewer | Overview, Voice & reports, Handover | Personal account; no owner settings or coordination-only controls | Hold decisions and recovery of existing unfinished reports within assigned scope |
| Organization owner | Operational destinations according to separately assigned role; Team and Settings | Members, employee activation/reset links, data policy, shifts, organization export | Ownership does not silently grant hold-clearance permission |

A real-member browser regression checks reviewer clearance and existing-note recovery while Add/Edit work, task assignment and late-file import stay absent. Backend tests enforce permissions independently of these controls.

## Capture and recovery

- Recording freezes the account, organization, work item, shift and displayed clarification context. Navigation cannot silently attach an existing recording to another item. Material clarification changes preserve the original question and require review.
- Audio and text drafts stay in account/organization-bound IndexedDB storage. Sending is explicit. Recordings checkpoint approximately once per second; abrupt closure can lose the final interval.
- After installation, the public application shell can reopen offline. Only minimal last-signed-in identity and assignment labels are cached for up to 72 hours. Offline capture clearly marks assignments as unverified. Private API responses, audio, credentials and CSRF tokens are not cached by the service worker.
- Reconnection requires a fresh session before normal workspace recovery and explicit sending. Ending membership clears the visible workspace and cached fallback identity. Backend authorization is checked again.
- Unsent spoken handover readbacks use a separate account/organization/shift store with the captured snapshot version and periodic checkpoints. Reload restores playback without submitting a receipt; a changed snapshot requires a new readback. They never enter the report outbox.
- Password changes preserve local drafts. Signout explicitly warns that this account’s unfinished recordings and drafts across all organizations will be removed from the device.
- A worker can download a private recovery file. An authorized supervisor can import it after the normal 72-hour upload window, preserving original author, shift, recording time and question. Imported text is a supervisor-supplied copy, not worker attestation. The backend verifies historical assignment.
- Existing saved-note recovery keeps completed transcription and human review history. Retrying does not invent content or silently change models.

## Setup and data boundaries

Organization dates are converted in the organization’s IANA timezone, independently of the device timezone. Ambiguous or nonexistent daylight-saving wall-clock times are rejected. A browser regression checks an India overnight shift from a UTC browser.

The global updated-time and practice-workspace banners remain removed. Recording policy is available in the owner’s Recording & data section. Strict pilot deployment blocks capture until the owner chooses a data policy. Real-data mode requires factory consent and separately approved provider configuration on the server; checking UI declarations alone does not enable provider access.

## Portal redesign, October 16, 2026

The portal uses the demo’s dark-green sidebar, cream background and restrained orange actions. Desktop navigation is 244px; normal content is capped at 1,200px, with forms capped at 560px. Controls use 16px input text and supporting copy uses 14px. Checkbox labels are clickable rows with 20px controls. The old competing portal CSS was removed from `platform.css` and consolidated in `workspace.css`.

| Screen | Implemented behavior | Verification |
|---|---|---|
| Overview | Shared summary cards, searchable work register, outstanding-work panel, work-item detail navigation | Desktop/mobile screenshots, existing filtering and work-item journeys |
| Record update | Select work, record, inspect transcript, send; work editing and offline recovery under More actions | Original WAV, transcript inspection, retry, recording-context and draft regressions |
| My work | Assigned tasks, completion reported versus supervisor verified, source access | Authenticated employee journey with Hindi default; backend assignment enforcement |
| Review | One source and decision dialog; protected decisions remain permission checked | Manufacturing, maintenance and warehousing recovery/review regressions |
| Handover | Unresolved items before reviewed items, source links, listening and separate acknowledgement | Stored snapshot, voice readback, stale versions and protected holds |
| Team | Searchable members with role and shift summary; one member editor; Members, Invitations and Access history | Invitations, replacement, activation, role edits and keyboard focus |
| Settings | General, Locations & teams, Shifts, Recording & data, Downloads; one section visible | Query-route restore, Back, checkbox sizing, timezone and export checks |
| Evidence | Chronological transcript, interpretation and decision entries; audio and collapsed provider metadata | Real stored-source assertions and populated timeline screenshots |
| Account/access | Existing five-field signup, login, recovery, activation and no-access routes retain compact forms | Original account/security journeys and mobile screenshots |
| Preview industries | No manufacturing workflow presented as available; team administration retained | Existing preview route and isolated demo tests |
| Setup | Workplace, team/work, first shift, optional invitations, recording policy | Interrupted setup, resource reuse, explicit assignment and policy save |

### Guided setup walkthrough

1. A new owner saves recovery codes and opens guided setup. An existing organization opens its normal workspace, with Continue setup while local setup completion is pending.
2. Save the workplace and location. Create or reuse the first team and work item.
3. Create or reuse a dated shift, select its supervisor and assign the work. Times use the organization timezone; overnight end dates are explicit.
4. Optionally add staff. Activation links do not make people active or assigned before they join. After activation, assign them through Settings > Shifts.
5. Explicitly save practice or real-data policy. Finishing the wizard does not bypass server provider/consent requirements.

Setup step and selected resource IDs are stored under account/organization-specific local-storage keys. Saved entities remain in authenticated server storage and are reused on return. Clearing browser storage loses the step marker, not those entities. Unsaved form text is not a saved server resource. The first-shift save retains its ID if assigning people fails, so retrying does not create a second shift. A lost network response before the server-generated ID reaches the browser can still require inspecting the existing shift list before retrying.

### Navigation and preservation

`?view=...` and `?section=...` are validated. Refresh restores the page and settings section. Back goes through the same recording, handover-readback and report-draft safeguards as sidebar navigation. Keep/Discard/Stay remain explicit. Workers have three bottom destinations on phones; supervisors and owners use a compact menu. Creating another organization is in the account menu.

No backend schema, provider credential, membership permission or stored operational record was changed for this redesign. The demo remains separate from private organizations. UI tests create fictional organizations in isolated test stores and use controlled providers or simulated microphone input.

### Evidence and limits

The screenshot collection is in `artifacts/portal/`, with an HTML contact sheet at `artifacts/portal/index.html`. Its `before` folder contains available historical reference screenshots, not a retroactively complete before-state matrix. The redesigned five principal owner pages are captured in English and Hindi at 390, 768, 1440 and 1920px, plus settings sections, dialogs, account/access and populated recovery states. Browser checks include keyboard dismissal, focus restoration and a 200% CSS-zoom layout check. Native browser zoom and assistive-technology sessions remain part of manual acceptance. They do not cover every possible combination of data, error and permission on every page.

Automated checks are implementation evidence, not proof of worker comprehension. Observed sessions with intended workers and supervisors remain pending. No human study, real-factory accuracy result or live-provider success is claimed by this redesign. Production-provider approval, real-device checks, deployment and retention gates remain as documented in the pilot runbook. The original 3D landing scene is preserved.

## Reproduce

From the repository root:

```sh
.venv/bin/pytest backend/tests -q --junitxml=artifacts/portal-backend-tests.xml
node scripts/check-translations.mjs
cd frontend
npm run build
npx playwright test --reporter=json > ../artifacts/portal-browser-tests.json
npx playwright test --config playwright.offline.config.ts --reporter=json > ../artifacts/portal-offline-tests.json
```

Final full checks: 261 backend tests, 39 browser tests, the production offline test, the translation audit and the production build passed. The responsive screenshot check was repeated after the final CSS adjustment. See `artifacts/portal-verification.json` for exact counts, timings and limitations. The production build still reports the existing large JavaScript chunk advisory; code loads the 3D scene separately. Browser simulations do not spend provider credits.
