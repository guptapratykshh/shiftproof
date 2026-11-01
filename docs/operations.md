# Operations and cost controls

## Local startup (AWS paused)

Keep SHIFTPROOF_ENV=local. Store GEMINI_API_KEY and GNANI_API_KEY only in the ignored .env. Confirm the Gemini project has no billing enabled before setting GEMINI_FREE_TIER_CONFIRMED=true. Run scripts/check_gemini.py; activate EXTRACTION_PROVIDER=gemini only when it passes, then restart FastAPI. The flag is a user assertion, not an API billing check. No automatic model fallback or billing activation occurs. HTTP 503 means provider unavailability; preserve the transcript and retry extraction later.

The AWS checks below are retained for a future deployment; no AWS changes were made for this upgrade.

## Archived cloud startup checks

- Confirm AWS credit balance, eligible services, account plan restrictions, and expiry in the billing console. Authentication does not establish credit coverage.
- Confirm Nova 2 Lite model authorization and a successful minimal invocation before selecting Bedrock mode.
- Configure the Gnani secret and run one short STT/TTS round trip. Measure programme-credit consumption, then reserve 30% for final demos.
- Open the frontend and check `/health`, `/config`, `/workspace`, and signed-in review permissions.

## Organization accounts

Signup creates an empty private organization. Invitations are manually shared, single-use, and expire after 72 hours. Real sessions use HttpOnly cookies with CSRF tokens; public HTTPS sessions are Secure. Email sending, email verification and social login are not enabled. Recovery uses the single-use codes saved at signup. Accounts on private localhost and the public preview are separate.

The `/demo` route retains fictional role selection. Never assign its identities to a private organization. Legacy private data can be imported only with `scripts/adopt_legacy_workspace.py --owner-email <existing-account-email> --organization-name <name>`. The tool preserves originals and creates a backup, with an idempotent import receipt.

Provider processing uses an installation-wide SQLite quota ledger shared by private and public servers. `MAX_MODEL_CALLS_PER_DAY` caps each model/speech counter; `MAX_ORGANIZATION_CALLS_PER_DAY` additionally caps each organization (default 50). Set `SHIFTPROOF_SHARED_USAGE_DB` explicitly when servers use different checkouts. These counters bound attempts; they do not enable provider billing or prove billing status.

## Controls included (legacy demo / archived AWS)

The backend defaults to 100 new notes, 200 model calls, and 200 speech calls per UTC day for the entire fictional workspace. These limits are transactionally persisted; failed calls still count. API Gateway limits bursts to 15 and steady traffic to five requests/second. SQS allows at most two concurrent consumers. CloudWatch logs retain seven days; a Lambda-error alarm is included without sending notifications to anyone.

Local and cloud quota values are configurable. No public endpoint can invoke extraction without a signed-in actor. Public question answering is deterministic and does not spend model tokens. Audio playback may consume network bandwidth. S3 recordings and DynamoDB data are retained until explicitly removed.

AWS budget alerts are delayed and are not hard spending caps. Set a budget in the account console, inspect actual usage daily, and keep the $90 reserve from the plan. No billing budget or credit coverage was assumed or asserted by the app. The SAM template avoids always-on servers, NAT gateways, and provisioned model capacity.

## Recovery

- If speech is transcribed but extraction is unavailable, the note becomes **manual review**, preserving the recording and transcript. A supervisor or quality reviewer can open **Review transcript manually**, add draft claims with exact supporting excerpts, or explicitly mark a microphone test as containing no operational update. Human interpretations are labeled and audited; quality clearance still requires the quality role. Retrying extraction reuses the saved transcript.
- `EXTRACTION_PROVIDER=scripted` only extracts the labeled samples; a configured Gnani key enables speech recognition but does not enable general extraction. Use the Gemini setup above locally. The remaining Bedrock notes describe the paused cloud path. For arbitrary automatic extraction, verify a successful Bedrock invocation before changing `.env` to `EXTRACTION_PROVIDER=bedrock` and restarting the backend. `Operation not allowed` together with `authorizationStatus=NOT_AUTHORIZED` requires resolving AWS model/account authorization; repeating recordings or changing the Gnani key cannot fix it. Check the model in the Bedrock console and contact AWS account support if authorization remains denied. No account-plan changes are performed automatically.
- A failed note remains on the voice-notes screen with an error, retry, and transcript revision controls.
- Review incomplete notes before acknowledging a handover. Discard is permitted only for unfinished notes without extracted claims; evidence attached to claims remains.
- Inspect Lambda logs, SQS age, and dead-letter messages after a processing outage. Requeue only after resolving the cause, using the original note ID.
- On a stale review (409), refresh and re-evaluate the newer evidence.
- Export the handover JSON before a demonstration. The report includes source references and explicitly identifies fictional data.

## Deployment and cleanup

`scripts/deploy.py` reuses the `shiftproof-demo` stack. `.local/deployment.json` contains non-secret resource outputs. `.local/demo-accounts.json` contains passwords and must never be committed or shared publicly. Rotate demo passwords through Cognito if needed.

To remove the hosted app, delete the CloudFormation stack in the AWS console. The evidence bucket and table intentionally have `DeletionPolicy: Retain`; deleting the stack alone does not delete data or stop their storage charges. Inspect and explicitly remove those retained resources and the artifacts bucket after exporting what you need. No cleanup is performed automatically.

Real organization endpoints now enforce tenant-scoped authentication and evidence authorization; anonymous/demo endpoints remain restricted to fictional data. See [organization operations](organizations-release.md). Before a real factory pilot, validate the workflow and operational requirements with its users. Obtain permission for recordings and define retention and deletion requirements with the pilot users.

## Share a temporary interactive preview

The public preview serves the built frontend and API together on port 8080. It uses a separate seeded SQLite database under `.local/public-preview`. Visitors can sign in with the operator, supervisor or quality demo roles, record notes, review reports and acknowledge handovers. The configured backend providers and existing daily quotas apply; API keys remain server-side. Existing private local recordings are not copied into this shared workspace. All visitors share demo records and demo identities. General extraction still requires the configured live-provider activation gate.

For a read-only preview instead, prefix the server command with `PUBLIC_PREVIEW_READ_ONLY=true`. That mode disables providers and rejects sign-in and changes.

```sh
(cd frontend && npm run build)
.venv/bin/uvicorn public_preview:create_app --app-dir scripts --factory --host 127.0.0.1 --port 8080
```

In another terminal:

```sh
cloudflared tunnel --url http://127.0.0.1:8080 --no-autoupdate
```

Share the HTTPS URL printed by cloudflared. Keep the Mac awake, online and both processes running. Stop cloudflared to end public access; a new quick tunnel gets a new URL. This is a temporary preview, not permanent hosting. See [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/). The normal private development app stays on port 5173 with its backend on 8000.
