# One-factory pilot runbook

The application is being prepared for one manufacturing pilot. A public demonstration is not a production deployment. Maintenance and warehousing remain demonstrations; the five preview industries are not operational workflows.

## Release gates

Do not collect real workplace recordings until the owner has approved the recording/retention policy, workers have been informed, and the host/operator has agreed to the support and recovery procedure. Do not send real data to the free/programme provider configuration. `store=false` does not change a provider’s contractual terms.

Before release, record evidence for all of these:

- Stable HTTPS domain on a persistent, single Linux host, monitored disk space, a named operator and an owner recovery code stored offline.
- Applicable Gemini and Gnani processing terms approved by the factory, separate approved business keys/model configuration, explicit account/provider budgets. This repository does not enable billing or AWS.
- Owner policy in `/organizations/{id}/pilot-policy`: real-data classification, factory approval, consent, retention days and spending/provider declarations. Server-side business flags and credentials must also pass; organization declarations alone do not unlock inference.
- Five intended workers and two supervisors complete the usability checklist in `docs/pilot-usability.md`. Wrong-item audio, lost submissions, unauthorized clearance or missed critical holds block release.
- A successful encrypted backup and restore drill on the actual host, load probe and restart drill, dependency review and acceptance of any remaining issue-register limitations.

Google’s [unpaid-service terms](https://ai.google.dev/gemini-api/terms) require particular care for confidential and personal data. Obtain Gnani’s applicable contract; a public privacy page is not a substitute. [Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/) are for development/testing. Neither approval nor a stable domain is implied by this repository.

## Local verification

```sh
.venv/bin/pip install -r backend/requirements.lock -e backend
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
cd frontend
npm ci
npm run build
npx playwright test
```

For a local persistent-host rehearsal, use a fresh data directory and scripted extraction. Existing `.local` records must not be overwritten:

```sh
SHIFTPROOF_DATA_DIR=/absolute/path/to/pilot-rehearsal EXTRACTION_PROVIDER=scripted SHIFTPROOF_DURABLE_JOBS=true PYTHONPATH=backend:scripts .venv/bin/uvicorn pilot_server:create_app --factory --host 127.0.0.1 --port 8090 --no-access-log
SHIFTPROOF_DATA_DIR=/absolute/path/to/pilot-rehearsal EXTRACTION_PROVIDER=scripted PYTHONPATH=backend .venv/bin/python -m shiftproof.worker
```

Both processes need identical provider and data-directory configuration. Live keys remain backend-only. An interactive fictional demo is at `/demo`; account routes use separate databases and audio directories. New organizations are empty. For the existing development servers, durable processing remains opt-in until a supervised worker is running.

## Persistent deployment package

`deployment/compose.yaml` contains an application, independent worker and Caddy HTTPS proxy. The application and worker share one local persistent volume. Do not use network filesystems or multiple hosts for these SQLite databases. The image compiles pinned SQLite **3.51.3**, verifies the source SHA-256 and asserts the runtime version before starting. Old local SQLite **3.50.4** uses rollback journaling; WAL is refused on unpatched versions. See the [SQLite WAL guidance](https://www.sqlite.org/wal.html#the_wal_reset_bug).

1. Copy `deployment/pilot.env.example` to `deployment/pilot.env`, use an approved owner email and exact HTTPS origin, and protect the file (`chmod 600`). Start with `EXTRACTION_PROVIDER=scripted` and fictional data.
2. Put `PILOT_HOST=your-approved-domain` in `deployment/.env`, point that domain at the host, and make ports 80/443 reachable. API port 8000 is not exposed to the public host.
3. Run `docker compose --project-directory deployment -f deployment/compose.yaml build`, then `... up -d`.
4. Check application/worker health, HTTPS Secure/HttpOnly cookies, invitation acceptance, signed-in access after refresh, and a complete fictional handover before real onboarding.
5. Build immutable image tags and record their digests for the release. The supplied base-image tags are not digest-locked; resolve and review digests on the actual deployment host before release.

Only the static proxy address `172.29.0.10` is trusted for forwarded scheme/client address. Do not change this to `*`. Access logs are disabled because activation/reset URL paths contain secrets; use non-secret application audit events. Configure host logs and firewall separately. No secrets, data volume or local recordings belong in the Docker build context.

## Onboarding and permissions

Owner signup uses name, email, password, confirmation and industry. The browser supplies timezone automatically; the owner can adjust it in Settings. Define a location, team, work item and dated shift. Use the next calendar date for an overnight end time.

Owners add workers by name and employee ID. They share 72-hour activation links manually; the worker chooses a password. Owners and supervisors use email accounts. After activation, assign workers to dated shifts and relevant work items. A worker without an assignment sees no operational records. Employee login/reset is scoped to that organization, never to another organization or the person’s email account.

Assign an incoming supervisor or explicit substitute, then link the outgoing handover to the incoming shift. Close a shift only after unfinished submissions have been reviewed, cancelled with a reason, or explicitly carried forward. Unresolved holds and tasks remain linked to their sources. A worker reports task completion; an authorized supervisor/reviewer verifies it. Completing an inspection task does not remove a hold.

See `docs/pilot-permissions.md`. Owner status alone never clears a hold. Changing a person’s permissions applies on their next request and before durable provider work. Revoked assignments also revoke historical snapshot/audio access when those receipts contain the removed work.

## Failed submissions and processing

The browser retains account/organization-scoped drafts in IndexedDB. Clearing browser data, uninstalling the browser or losing the phone can still remove unsent drafts; these are not server backups. Only drafts explicitly marked for sending are eligible for submission, and online authorization is required. A cancelled or timed-out upload can safely retry the same capture/audio digest.

- Transcription succeeded, extraction failed: retry extraction from the saved transcript; do not re-transcribe it.
- Requester removed: a supervisor opens the saved note and records a takeover, cancellation or carry-forward reason. Original authorship and audio stay unchanged.
- Server/worker restart: expired leases become eligible again. Completed transcription stays saved; a fenced old worker cannot overwrite a new lease. Network attempts are persisted and bounded; explicit retry is recorded separately.
- Stale clarification: retain the exact old question and answer. A client-held historical question is unverified context and requires manual interpretation, not automatic inference against a newer question.
- More than 72 hours late: the ordinary submission is refused with the draft retained. Use supervisor-assisted recovery; do not change the recording timestamp to make it appear recent.
- Source transcript changed after review: earlier interpretations remain in history and readiness is blocked until those interpretations are reviewed against the new source.

Monitor locally:

```sh
PYTHONPATH=backend .venv/bin/python scripts/pilot_health.py
PYTHONPATH=backend .venv/bin/python scripts/pilot_retention.py ORGANIZATION_ID
```

The health command reports heartbeat age, pending-job age and authorization-blocked jobs without transcripts. Alert on a missing/old worker heartbeat, jobs older than ten minutes, repeated provider errors and host disk usage above the agreed limit. The retention command is an inventory; it does not silently erase evidence. A reviewed deletion/export procedure and backup-expiry policy must be agreed before real collection.

## Backups, restore and rollback

Backup keys must be stored separately from backups. The tool uses authenticated AES-256-GCM, manifest hashes and SQLite’s backup API; restoration rejects tampering and existing destination directories.

1. Generate a key once with `scripts/pilot_backup.py keygen --key-file /secure/shiftproof.backup.key`.
2. Pause application and worker together. Confirm no other process writes the data volume. Keeping the proxy up with a maintenance response is optional; never accept writes during the consistent multi-database snapshot.
3. Run `scripts/pilot_backup.py backup --source /persistent/data --destination /offhost/DATE.backup.enc --key-file /secure/shiftproof.backup.key --services-stopped` using the project Python environment.
4. Restart services and check health. Schedule this daily with your host’s scheduler, copy the encrypted archive off-host, and expire backups according to the agreed policy.
5. Restore monthly to a **new** directory using the `restore` action with the same flags. Run integrity checks, source playback, an old acknowledgement and login checks against that copy. Record the result; never test restoration over the live directory.

Before upgrading, take a backup and retain the previously built image. Workspace normalization preserves the original JSON row as a migration archive; the identity migration preserves IDs and creates a pre-migration SQLite backup. Those archives are not a substitute for a coherent full backup. For rollback, stop both processes, restore the pre-upgrade backup into a new volume, and run the previous compatible image against it. Never run older code on a database changed by newer code merely because the old JSON row remains.

### Scheduled backups on the pilot host

`deployment/backup.sh` and the supplied systemd service/timer provide a daily backup job. The wrapper checks Docker configuration, stops both writers, runs the encrypted backup in the application image and restarts services even when backup fails. Agree the brief write outage with the factory. The timer defaults to 03:00 in the host timezone; change it to the agreed maintenance window.

Before enabling it, create `/etc/shiftproof/backup.env` containing absolute `PILOT_DEPLOYMENT_DIR`, `PILOT_BACKUP_KEY` and `PILOT_BACKUP_DIRECTORY` paths. Keep the key outside the application data volume and backup directory. The container runs as UID 10001: grant that identity read access to the key and write access to the backup directory without making either public. Adjust the service's `/opt/shiftproof` checkout path, install the units and run a manual service/restore drill before `systemctl enable --now shiftproof-backup.timer`. Monitor failed service status and missing daily archives; do not treat timer installation as proof of a recoverable backup. An off-host destination or separate encrypted archive transfer is still required. These Docker/systemd operations have not run on this Mac.

## Explicit limits

This is one-host pilot software, not an availability or capacity guarantee. Response latency and contention must be measured on the deployment host. The benchmark validates manufacturing simulations only. Phone storage durability and microphone behavior require real-device sessions. Email delivery, SMS, scheduling automation, ERP integration, AWS deployment and the five preview industries remain deferred.
