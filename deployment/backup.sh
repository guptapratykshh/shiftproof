#!/bin/sh
# Scheduled consistent backup. Validate on the actual Docker host before enabling.
set -eu
PILOT_DEPLOYMENT_DIR=${PILOT_DEPLOYMENT_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)}
: "${PILOT_BACKUP_KEY:?Set an absolute path to the separately stored 32-byte backup key}"
: "${PILOT_BACKUP_DIRECTORY:?Set an existing off-volume backup directory}"
case "$PILOT_BACKUP_KEY:$PILOT_BACKUP_DIRECTORY" in /*:/*) ;; *) echo 'Backup paths must be absolute' >&2; exit 2;; esac
test -f "$PILOT_BACKUP_KEY"
test -d "$PILOT_BACKUP_DIRECTORY"
compose() { docker compose --project-directory "$PILOT_DEPLOYMENT_DIR" -f "$PILOT_DEPLOYMENT_DIR/compose.yaml" "$@"; }
# Fail before stopping the service when configuration/daemon is unavailable.
compose config --quiet
docker info >/dev/null
PILOT_BACKUP_NAME="shiftproof-$(date -u +%Y%m%dT%H%M%SZ).backup.enc"
resume() {
  status=$?
  trap - EXIT INT TERM
  compose up -d app worker || status=1
  exit "$status"
}
trap resume EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
compose stop app worker
compose run --rm --no-deps \
  -v "$PILOT_BACKUP_KEY:/run/backup.key:ro" \
  -v "$PILOT_BACKUP_DIRECTORY:/backups" \
  app python /app/scripts/pilot_backup.py backup --source /data \
  --destination "/backups/$PILOT_BACKUP_NAME" --key-file /run/backup.key --services-stopped
