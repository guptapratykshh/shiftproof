# Voice reporting verification

Updated 2026-10-19. This is an engineering report, not pilot acceptance.

## Simple reporting and whole-report review (2026-10-19)

Four warehousing reports had been explicitly closed without operational claims, despite explanations saying dispatch was ready. Closing the note had never created facts. The supervisor form made this distinction too easy to miss. No existing private report was approved, reopened, discarded or reinterpreted by this implementation.

### Changes delivered

- One report dialog shows the original recording, transcript and workflow questions. Explicit per-fact decisions save atomically through the existing evidence and reconciliation rules. Empty decisions are rejected. Routine checks offer a selectable reason; conflicts and protected clearance require a specific explanation.
- Closing a report with no work update now requires a separate explicit choice and explanation. A scoped supervisor can reopen an incorrectly closed report, preserving the earlier closure and evidence. Reopening grants no approval. Warehousing document verification cannot be inferred from a quality-check statement.
- Organization owners can grant shared-phone assistance for specific assigned shifts. Both helper and worker must belong to the organization and be assigned to the selected work. The authenticated helper remains the accountable submitter. The report stores the worker separately as `reported_by` and the helper as `assisted_by`. Upload, processing and provider work recheck access.
- Worker selection shows name and a short identity suffix. Capture confirms the name and work. Drafts, offline recovery and recording checkpoints retain both identities. Switching workers stops playback and hides the previous worker's drafts. Local device speech reads the selected identity when a matching installed voice exists; otherwise a readable confirmation remains.
- Worker receipts update with checked, partially checked or help-needed status, including assisted reports attributed to them. Workers and assisted capture use Speak, Listen and Send. Sending a recording does not require editing a transcript. Provider failures remain submitted reports in the supervisor queue. Original recordings and delivery receipts remain available.
- A deterministic bilingual summary supplies both screen and handover speech: reported facts, checked facts and remaining requirements. Source links remain under Details. Protected holds survive ordinary packing/dispatch checks.
- Visible online screens poll every four seconds and refresh after changes/reconnect. Status refresh does not replace capture input. Organization/shift/request fences reject obsolete responses. Speech is bound to summary version and language; the server rechecks authorization/version after synthesis, and the client rejects or stops obsolete playback.
- Original-source playback now stops competing audio without stopping itself. Technical microphone controls are under Help while the level meter remains visible.

### Interfaces

New scoped endpoints: `POST /organizations/{org}/notes/{note}/review`, `POST /organizations/{org}/notes/{note}/reopen`, and `GET/PUT /organizations/{org}/assisted-capture`. Review accepts an expected version, idempotency request ID and explicit decisions. Notes add optional reporter/helper identities and progress. Workspace responses add a versioned bilingual summary. Speech accepts `language` and returns `X-Summary-Version` and `X-Summary-Language`. Existing single-claim review endpoints remain available. Empty legacy manual review now requires `no_operational_update=true`; silence or an empty form is not consent to close a report.

### GUI steps actually performed

The localhost walkthrough used a new fictional warehousing workspace and a deliberately seeded provider-failure state, not the user's private reports. Setup data was created through authenticated APIs; review and playback were exercised through the browser.

1. Opened Voice & reports and clicked **Listen and check**.
2. Selected **Checked against the recording** and pressed **Save checked updates** without choosing facts. The form refused the empty review.
3. Selected packing complete and dispatch ready, marked each Correct, and saved once.
4. Opened Handover. The shared summary showed packing and dispatch checked, with dispatch documents still requiring verification.
5. Clicked **Listen to handover**. Live Gnani Timbre returned HTTP 200 and summary version 5. The browser decoded a 9.12-second clip, advanced playback and reported no playback error. This confirms browser playback, not physical audibility on the user's device.

Additional browser journeys use separate worker and owner sessions. The worker sends a report; the owner reviews it; the worker sees the updated summary without a manual refresh. They also exercise reopening a mistaken closure, owner-granted assistance, worker switching, saved-draft recovery and checkpoint attribution. Provider inference in automated journeys is controlled/scripted and is not a live model-accuracy claim.

Artifacts: [localhost handover](../artifacts/simple-review-live-handover.png), [review screen](../artifacts/simple-review-live-owner.png), [worker screen](../artifacts/simple-review-worker.png), [assisted capture](../artifacts/simple-review-assisted.png), [GUI walkthrough video](../artifacts/simple-review-walkthrough.webm). The video demonstrates fictional review/recovery with live TTS; it is not an original human voice-to-ASR demonstration and does not prove physical audibility.

### Verification and limits

Current machine-readable totals and logs are in [simple-review-results.json](../artifacts/simple-review-results.json). The final full browser run passed 50/50 scenarios in 2.6 minutes; production offline recovery passed 1/1. The focused source-playback journey also passed separately. Backend suite: 282 passed, including atomic rollback, scoped access, reopen history, stale speech, idempotency, assisted attribution and selected-task completion remaining unverified. Browser test fixtures reset authentication attempt counters between independent scenarios only in their isolated test database. This avoids 50 unrelated scenarios sharing the production 30-signup/five-minute IP budget; application rate limits remain unchanged. The production build and translation audit pass. Build still reports large bundle warnings; two dependency deprecation warnings remain in backend tests.

The four affected private reports remain available for explicit reopening and review. A supervisor should select only statements actually supported by each recording. An authorized reviewer must separately verify dispatch documents or quality clearance. No existing quality statement was converted to warehouse document verification.

Physical-microphone confirmation, a fresh live Prisma/Gemini journey, and observed sessions with five intended workers and two supervisors remain pending. The previous broader live model smoke check below still has unresolved failures. Controlled browser checks, successful TTS and software tests do not establish pilot readiness or worker comprehension. No AWS, model, billing or provider-data approval settings were changed.

Reproduce software checks:

```sh
.venv/bin/pytest backend/tests -q
npm --prefix frontend run build
node scripts/check-translations.mjs
cd frontend
npx playwright test --reporter=list
npx playwright test --config playwright.offline.config.ts --reporter=list
```

## Follow-up: repeated clarification and submitted draft loop

Read-only inspection found three saved clarification replies in manual review after invalid model output, plus unfinished transcript-review notes. Their audio/transcripts had not disappeared. The capture form only retired local drafts after successful extraction, so provider failure kept a submitted report in the draft-navigation guard. Late autosaves could also recreate a retired draft. The question generator did not distinguish a missing answer from an answer awaiting review. Handover acknowledgement correctly blocked unfinished reports but offered no direct review route.

Changes:

- Accepted extraction requests record the submitted revision. The browser retires the capture after server acceptance, even when interpretation needs human review. Existing ghost drafts are checked against the authenticated saved note on restore; changed unsent text remains a draft.
- IndexedDB uses content-free retirement markers so delayed autosaves cannot recreate sent or discarded captures. Other drafts remain untouched. Autosave callbacks are fenced to their original capture ID.
- Clarifications include answer/review progress and source note IDs. Answered questions stop inviting duplicate replies. Reviewing an answer does not release protected holds; new unrelated evidence can reopen a question.
- Handover lists the blocking sources and opens a focused report review. Manual interpretation, retry and audited carry-forward remain available to authorized roles. Acknowledgement is explicitly receipt of information, not completion or clearance.
- Clarification responses must include `context_refs` in their transport schema. Backend validation still rejects missing or invented question references. A more constrained array schema returned HTTP 400 and was removed; temporary HTTP 503 failures were also observed. The compatible schema passed the fictional live clarification check on the configured model without repair. This is one development case, not general accuracy evidence.

Verification: 274 backend tests passed; the subsequent focused backend run passed 26 tests after simplifying the transport schema. All 48 browser tests passed, including the worker submission/navigation flow, stale-draft recovery, protected holds, manual review from handover and late-autosave prevention. Production offline recovery passed, as did the build and translation audit. Results: `artifacts/submission-flow-backend.xml`, `artifacts/submission-flow-browser.json`, `artifacts/submission-flow-offline.json`, and `artifacts/clarification-validation-after.json`. The rejected-schema and service-unavailable results are retained separately. Reproduce the live fictional case with `.venv/bin/python scripts/check_clarification_flow.py`.

Existing operational records were not approved, discarded or reprocessed automatically. Old failed replies still need a supervisor to retry or interpret their saved transcripts. Quality clearance still requires an authorized reviewer. API and processing workers were restarted to activate the changes.

## Follow-up: repeated silence and missing indicator

The user reported that the earlier restart and dual-path recorder did not resolve the physical microphone problem. Inspection found an unbounded `AudioContext.resume()` before native capture initialization and a level display dependent on worklet messages. These are reproduced software failure paths, not a confirmed diagnosis of the user's device.

The recorder now starts native capture independently, bounds initialization, uses an analyser plus decoded native samples for feedback, and decodes recorded containers through an offline context. It does not force a mono input device; conversion to mono WAV selects the strongest channel. A suspended audio context has an explicit enable action. Permission denial, unavailable devices and silent input are distinct visible states. Permission requests that resolve after timeout release their tracks.

The indicator now uses visible segmented bars with an accessible meter and a short status. Technical diagnostics remain expandable. Existing audio and drafts remain intact.

Seven targeted browser tests passed, including injected suspended-context and worklet-load failures, an actually moving meter, permission rejection, silence rejection and saved task context. The screenshot `artifacts/microphone-indicator.png` uses controlled browser audio, not the user's microphone. Latest full-suite results are in `artifacts/microphone-fix-browser.json`, with production offline recovery in `artifacts/microphone-fix-offline.json`.

The full run passed 45/46 checks; the remaining test read claims before asynchronous processing finished. After adding an explicit wait for claims, all seven microphone tests passed in `artifacts/microphone-fix-targeted.json`, including the previously failing worker flow. The worker's visible live meter is captured in `artifacts/microphone-worker-recording.png`. Production offline recovery passed 1/1; the build and translation audit passed. No claim of a single clean 46-test rerun is made.

The browser APIs used are documented in [MediaRecorder](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder), [AnalyserNode](https://developer.mozilla.org/en-US/docs/Web/API/AnalyserNode) and [OfflineAudioContext](https://developer.mozilla.org/en-US/docs/Web/API/OfflineAudioContext). Actual device playback remains an acceptance gate.

## Reproduced issues and changes

| Issue | Change | Status |
| --- | --- | --- |
| A stored WAV contains only zero-valued samples | Reject silent audio before transcription; retain the source and identify the failure | Covered by backend and browser checks |
| The user's selected microphone still gives a flat meter | Native-rate capture, direct MediaRecorder path plus PCM fallback, microphone selection, local test playback, disabled echo cancellation/noise suppression | Controlled inputs pass; physical microphone remains unverified |
| Recorder previously presented silence as ready | Signal meter, silence rejection, quiet-audio warning and capture interruption diagnostics | Implemented |
| Capture shutdown can omit queued frames | Flush worklet frames, finalize native recording, encode mono 16 kHz WAV, release tracks | Controlled browser check passes |
| Replacement recording can discard completed work | Keep the previous recording until a replacement succeeds; preserve acknowledgement checkpoints during replacement | Implemented |
| Workers cannot link spoken completion to an assigned task | Freeze task context in note/draft; validate assignment; record explicit completion with source revision | Tested using authenticated sessions and controlled extraction |
| Completion could be confused with verification | Only mark reported complete; supervisor verification remains separate | Tested |
| Revised completion evidence can leave unsupported task decisions | Reopen dependent task decisions for reconciliation, preserve audit history | Tested |
| Failed extraction appears to lose a report | Retain audio/transcript/task context; make saved failure visible in scoped owner/supervisor views | Backend and browser coverage |
| A development origin can retain an old offline shell | Clear only ShiftProof shell caches and its service worker during development; retain IndexedDB drafts | Implemented; production offline support preserved |

## Verification evidence

- Backend: 272 tests passed. Machine-readable results: `artifacts/voice-backend-tests.xml`.
- Recording/browser targeted checks: four passed, including sound, silence, local microphone playback and task-context recovery after refresh.
- Full browser results: `artifacts/voice-browser-final.json`.
- Production offline results: `artifacts/voice-offline-final.json`.
- Production build and translation audit passed. Build still reports large bundle warnings.
- Screenshot of the worker task-report journey: `artifacts/voice-task-worker.png`.

Live integration used fictional synthesized Hindi speech. Timbre produced non-silent audio, Prisma transcribed it, and Gemini extracted packing complete and quality pending. See `artifacts/voice-live-speech.json`. This is not evidence that the user's physical microphone works.

Five fictional selected-task text cases matched expected completion outcomes: done, negative, future, conditional and ambiguous. See `artifacts/voice-live-tasks.json`. This checks the completion field only; the model also emitted a redundant task claim in one response, so it does not establish full extraction correctness.

The broader live extraction smoke check is **not passing**. The initial run matched 11/12 cases and omitted an inspection task. After a prompt change, nine of ten returned cases matched; the conditional case differed, invalid model output stopped the run and two requested cases were incomplete. Preserve both `artifacts/voice-gemini-smoke-initial.json` and `artifacts/voice-gemini-smoke.json`. A subsequent two-case diagnostic is in `artifacts/voice-validation-diagnosis.json`. Do not describe the current model configuration as verified or omit these failures from evaluation.

## Reproduction

Run from the repository root unless stated otherwise:

```sh
.venv/bin/python -m pytest backend/tests --junitxml=artifacts/voice-backend-tests.xml
npm --prefix frontend run build
node scripts/check-translations.mjs
cd frontend
PLAYWRIGHT_JSON_OUTPUT_NAME=../artifacts/voice-browser-final.json npx playwright test --reporter=json
PLAYWRIGHT_JSON_OUTPUT_NAME=../artifacts/voice-offline-final.json npx playwright test --config=playwright.offline.config.ts --reporter=json
```

Optional live checks consume provider quota and use the configured model without changing billing:

```sh
.venv/bin/python scripts/check_voice_capture.py
.venv/bin/python scripts/check_task_completion.py
.venv/bin/python scripts/check_gemini.py
```

## Remaining acceptance gates

The user reported silence even with the correct microphone before the alternate capture path was added. The subsequent real-device check is pending. Restarting services or passing fake-input browser tests does not resolve that uncertainty. A newly captured audible user recording must pass transcription, submission, assigned supervisor/owner visibility, review and handover before the voice workflow can be accepted end to end.

Protected holds still require authorized review. Task completion does not clear quality holds. No changes to AWS, billing or the configured provider model were made. Existing private recordings and organization records were preserved.

## Live browser verification, 16 October 2026

This check used the real localhost application in separate headed Chromium windows, not a Playwright test case or API-seeded workflow. All signup, employee activation, invitations, shift assignments, report submissions, review decisions, recovery and acknowledgement actions were performed through visible web controls. The isolated fictional organization is `org_893a01b2d1f04f3f`. Private organization records were inspected read-only and were not changed.

The user's existing supervisor decisions were present. Packing and dispatch had been confirmed; separate quality-clearance drafts and four unfinished current-shift reports remained. Carrying a report forward did not approve it. These were distinct outstanding items, not lost supervisor decisions.

Browser journey completed:

1. Created an owner account and configured a location, team, batch and dated shift using guided setup.
2. Activated an employee-ID worker and an email supervisor, assigned both to the shift, and explicitly gave the owner authorized-reviewer permission.
3. The worker submitted fictional Hinglish text reporting packing complete and quality pending. Live Gemini extracted both sourced claims. The supervisor reviewed each through the UI; the quality hold remained.
4. The worker answered the displayed quality question. Live Gemini interpreted the new clearance report. Navigating after sending produced no discard dialog.
5. The supervisor's clearance-confirmation option was disabled. The authorized reviewer was also blocked until explicitly selecting the earlier pending report to supersede. After that decision, the batch showed Requirements reviewed.
6. The supervisor acknowledged the handover. Refresh preserved the current receipt. The worker no longer saw the answered question.
7. A browser-level network interruption deliberately blocked processing of a duplicate after its transcript was saved. No provider response was mocked. The supervisor closed this unfinished duplicate with a reason. The worker reopened its saved local draft; it was recognized as closed, not resent, and navigation had no discard loop.
8. The material update required a new acknowledgement. The supervisor acknowledged the new version. English and Hindi handover screens were inspected.
9. Opening the original evidence showed both the original supervisor decisions and the later authorized supersession decision.

Two successful live extractions used the unchanged `gemini-3.5-flash-lite` model, with stored processing latencies of 6,628 ms and 3,487 ms. These are individual observations, not an accuracy benchmark or a latency percentile. Inputs in this run were typed fictional Hinglish; this does not verify the physical microphone or constitute a human usability study.

Corrections made during this check:

- Show saved review decisions, responsible reviewer and remaining claims directly in handover and report review.
- Continue from manual interpretation into the required claim-review step instead of closing the flow without explaining what remains.
- Update a fully reviewed note's processing stage to complete.
- Select supersession candidates from the reviewed batch, even if a different batch is selected for capture.
- Identify quality-only conflicts and clearance reviews as requiring a quality reviewer.
- Expose audited closure for duplicate or irrelevant unfinished reports, retaining original evidence.
- Recognize closed server reports when restoring stale local drafts; preserve any unsaved changes or unuploaded audio.
- Include decisions that supersede the original report in its evidence history.

Machine-readable browser evidence: `artifacts/browser-human-verification.json`. Screenshots include `browser-supervisor-reviews.png`, `browser-supervisor-clearance-restricted.png`, `browser-authorized-clearance.png`, `browser-review-evidence-history.png`, `browser-closed-draft-recovery.png`, and `browser-handover-final.png` / `browser-handover-final-hindi.png`.

To reproduce manually, use the same nine steps above in a new fictional organization on localhost. Do not approve private quality reports or close other people's unfinished reports merely to make the screen appear ready. Existing approvals and provider restrictions remain enforced.

Final regression verification after the browser walkthrough: **274 backend tests, 48 browser tests and one production offline check passed**. The build and translation audit passed. Reports are `artifacts/browser-review-backend.xml`, `artifacts/browser-review-final.json`, and `artifacts/browser-review-offline.json`. The first browser run had five failures because old tests expected the review dialog to disappear; those tests were updated to follow the visible saved-decision screen and the full suite was rerun successfully. The original failed run remains in `artifacts/browser-review-regressions.json`.
