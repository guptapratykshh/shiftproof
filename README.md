# ShiftProof

Hindi/Hinglish voice handovers that keep original evidence, reconcile conflicting reports, and preserve unresolved work.

**ShiftProof now includes real organization accounts and three working industry profiles: manufacturing, equipment maintenance and warehousing.** Five additional industries are clearly labeled previews. The public demo has been removed. Operational data and editing require an organization account. Old `/demo` links redirect to sign-in. See the [organization release report](docs/organizations-release.md) for authentication, isolation, screenshots and verification. Scripted text mode runs without model credentials. Live audio requires a Gnani key; general automatic extraction uses Gemini. React, FastAPI and SQLite run locally; AWS integration is paused. See the [implementation and re-rating report](docs/re-rating-report.md). Arbitrary transcripts can be reviewed manually when extraction is unavailable. Scripted fixtures, human-entered claims, and measured engine checks are explicitly labeled in the interface.

**Local app:** http://localhost:5173. The separate interactive public organization site runs on port 8080; temporary tunnel links are local development links and are not permanent hosting. AWS hosting is archived and was not updated in this delivery.

## Manufacturing pilot work

The website uses a shared plum/lavender design with light and dark appearance. Workers have three Hindi-first destinations: Home, My work and Handover. Recording follows Record, Listen/check and Send, with optional transcript review before sending. Management has a separate work register and Reports & evidence queue. Dated shifts, assignment checks, employee-ID accounts, resumable jobs and local drafts are preserved. Owners retain people/settings/export controls; ownership alone does not grant operational review or protected-clearance permission.

Local redesign walkthroughs use a test microphone and labeled transcription fixtures, not live provider inference. Historical reports in `docs/` reference locally generated files under `artifacts/`; those screenshots, recordings and logs are not included in this public repository. Run the verification commands below to generate your own results. The reference in `shift-proof-ui-redesign` is a visual prototype; the running application remains React/Vite in `frontend`, backed by the existing FastAPI services.

Start with the [pilot implementation report](docs/pilot-implementation.md), [permission matrix](docs/pilot-permissions.md), [deployment/recovery runbook](docs/pilot-runbook.md) and [observed usability checklist](docs/pilot-usability.md). This is pilot preparation, not a claim of factory validation. Real-provider approval, a stable HTTPS host and intended-worker sessions remain release gates. Free-tier providers remain for fictional data only.

## Run locally

Requires Python 3.12+ and Node 20.19+. Run `bash scripts/dev.sh` to start the API, durable processing worker and frontend together. The separate commands below retain inline development processing unless `SHIFTPROOF_DURABLE_JOBS=true` is set; when enabled, also run `.venv/bin/python -m shiftproof.worker` in another terminal.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -e './backend[dev]'
test -f .env || cp .env.example .env
.venv/bin/uvicorn shiftproof.api:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open **http://localhost:5173** for the 3D landing page, **/signup** to create an organization, or **/signin** to choose worker, supervisor or organization sign-in. Save the one-time recovery codes shown at signup.

Signup asks for name, email, password, confirm password and organization type. Workspace name and timezone are automatic and can be changed by the owner in Settings. Owners add named team members through activation links, manage operational roles in People & access, and download workspace records from Settings. Hold clearance remains an explicitly assigned reviewer permission. See the [team walkthrough and feature-parity checklist](docs/organizations-release.md#team-management-walkthrough-and-feature-parity).

Organization workspaces provide worker Home, My work and Handover; supervisors have Overview, Work items and Reports & evidence; owners additionally manage Team and Settings. The existing recording, human review, recovery, protected-clearance and acknowledgement workflows remain available through authenticated organization routes.

New private workspaces persist under `.local/accounts/organizations/<organization-id>/`; their records, recordings and snapshots require membership. Previously stored demonstration data is retained on disk but has no public API or user interface. Legacy `.local/shiftproof.sqlite3` and `.local/notes/` are preserved and never assigned to the first signup. Use the explicit local ownership-import command in [the release report](docs/organizations-release.md). Public-preview accounts use a separate `.local/public-preview/accounts/` namespace. This remains a local prototype, not a clinically validated or production-operated service.

## Configure live extraction

Keep secrets only in the ignored backend `.env`; `.env.example` contains blank placeholders. Preserve an existing `.env` when updating the project.

```dotenv
SHIFTPROOF_ENV=local
GNANI_API_KEY=<your Gnani key>
GEMINI_API_KEY=<your Gemini key>
GEMINI_MODEL_ID=gemini-3.5-flash-lite
GEMINI_FREE_TIER_CONFIRMED=true
EXTRACTION_PROVIDER=scripted
```

Set the free-tier flag only after checking that the Gemini project has no billing enabled. It records your assertion; the application cannot verify billing from an API key and never enables billing. Run:

```sh
PYTHONPATH=backend .venv/bin/python scripts/check_gemini.py --model gemini-3.5-flash-lite --activate
```

The command activates the explicitly selected model only after all 12 development checks pass; restart FastAPI afterward. Cases cover Hindi future completion, Hinglish negation, number corrections, conditions, clarification replies, wrong batches and non-operational speech. Runtime processing never silently switches models. A 503, quota failure or malformed response retains the transcript for retry/manual review. `scripted` processes only exact labeled samples; configuring speech alone does not enable general extraction.

Prisma uses 16-bit mono WAV and `hi-IN`; Timbre uses `timbre-v2.5`, voice Nalini. Real saved recordings have Prisma transcripts and request IDs. A live Timbre check on October 13 produced a valid 24 kHz, 3.52-second WAV. The authorized alternative `gemini-3.5-flash-lite` passed all 12 live smoke cases on October 16 (IST) and is pinned locally. The earlier REST response parser defect was fixed. Free-tier quotas can still interrupt processing; see the dated report for measured comparison status.

## Test and evaluate

```sh
.venv/bin/pytest backend/tests -q
.venv/bin/python evaluation/run.py --mode engine
cd frontend
npm run build
npx playwright install chromium
npm run test:e2e
```

The 60 synthetic scenarios contain 20 development and 40 held-out **template variants**. They are useful contract checks, not an independent language benchmark. Engine mode consumes supplied structured claims and does not measure STT, extraction, or user impact. `evaluation/scenarios.json` is checked in; do not regenerate it after freezing a genuine evaluation set.

The separate frozen language dataset has 60 authored situations (20 development, 40 held out), with independent Hindi annotation pending. Run the production services with supplied gold claims to verify the evaluation plumbing:

```sh
PYTHONPATH=backend .venv/bin/python evaluation/language_run.py --mode contract --split all --output evaluation/results/my-contract-run
```

Once the Gemini smoke test passes, run the matched comparison using free quota:

```sh
EXTRACTION_PROVIDER=gemini .venv/bin/python evaluation/language_run.py --mode live --split development --max-calls 100
EXTRACTION_PROVIDER=gemini .venv/bin/python evaluation/language_run.py --mode live --split held_out --max-calls 200
```

Runs resume validated cached responses and refuse mixed dataset/model/code identities. Failed provider cases remain in requested denominators. Do not equate contract-mode accuracy with language accuracy. Human recording assignments, blind annotation sheets and usability worksheets are prepared; participation and results are pending. See the [evaluation protocol](docs/evaluation.md).

## Archived AWS deployment workflow (paused)

AWS remains paused. Historical deployment scripts target the retired demonstration API and must not be used to publish the current organization application. Use the [persistent-host runbook](docs/pilot-runbook.md) instead.

## Engineering boundaries

- LLM output is a candidate. Only authorized human review gives it the stored confirmed status, displayed as Human-reviewed; this does not establish objective truth.
- Clearing or rejecting a quality hold requires the quality role. Packing and dispatch claims cannot clear it.
- Conflicting values must be explicitly superseded, preserving old claims and transcript versions.
- Late explicitly dated observations cannot replace newer reviewed observations. Unknown event times stay unknown.
- Evidence is an exact transcript excerpt linked to a whole short recording; there are no invented word timestamps or confidence scores.
- SQLite uses serialized transactions locally; DynamoDB uses version-checked transactional writes in AWS.
- Queued processing uses stable note/revision IDs and a processing lease. Provider calls may still be repeated after a crash before checkpointing; exactly-once billing is not claimed.
- Questions are limited to deterministic pending/hold/change intents. Arbitrary factory advice, machine control, ERP actions, and voice identity are out of scope.
- Typed readback is recorded; semantic understanding and physical completion are not automatically certified.
- No human research, social post, or competition submission has been performed by these scripts.

See [architecture](docs/architecture.md) and [submission checklist](docs/submission.md). Historical delivery reports describe earlier versions; current behavior is documented here.


## Local review without AWS

Keep `SHIFTPROOF_ENV=local`. Use `EXTRACTION_PROVIDER=gemini` after a successful smoke test, or explicitly choose `scripted` for fixture-only development. Gnani can transcribe real recordings with your backend key. Unsupported or failed extraction remains recoverable from the saved transcript.

Sign in to your organization as a supervisor or authorized reviewer, open **Reports & evidence → Listen and check**, and review the source and proposed statements. Select current, planned, or conditional meaning explicitly. A quality release still requires the quality role. For a microphone test, enter a review reason and mark **no operational update**. Original audio and transcript stay in history. You can retry extraction after configuring a working model, without recording again.


For public interactive access with isolated visitor data:

```sh
npm run build --prefix frontend
.venv/bin/uvicorn public_preview:create_app --app-dir scripts --factory --host 127.0.0.1 --port 8080
# In another terminal; keep both processes running:
cloudflared tunnel --url http://127.0.0.1:8080 --no-autoupdate
```

Visitors sign up or accept an invitation and edit records according to their organization permissions. `.local/public-preview/` retains existing public organization accounts and stays separate from the private localhost workspace. Anonymous operational APIs and demo role switching are removed. Tunnel URLs are temporary; restarting the tunnel creates a new link. No keys are exposed to the browser.
