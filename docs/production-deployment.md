# Stowarr production deployment and rollback

## Qualify the release in staging

1. Record the candidate commit, current production commit and image IDs, the
   production Compose project, and the person approving the rollout. Keep the
   known-good images and Compose definitions available for rollback.
2. Use an isolated staging checkout, project, data directory, service network,
   and loopback port. The base Compose file declares a fixed
   `media-optimizer` name and an external `arr-stack_default` network.
   Use a separate Docker host or verify that staging overrides isolate both
   before starting containers. Use disposable databases, test credentials,
   and staging-only Radarr and qBittorrent endpoints.
3. Run `sh scripts/validate.sh config/config.example.yaml` and render the
   staging Compose model with `docker compose ... config --quiet` using both
   Compose files. Verify the three general write gates are false and confirm
   the staging executor's client ID, dedicated category, endpoint, and eligible
   Jellyfin user. The executor can submit an approved release even when the
   general write gates are false.
4. Rehearse the UI upgrade and rollback on staging. Verify private access, a
   successful authenticated page load, readable state and approval schemas, and
   stable service state. Use an empty approval queue or staging-only fixtures.
   If exercising an approval, verify that it targets a disposable test release
   and that reconciliation records its expected outcome without replay.
5. Obtain production rollout approval after reviewing staging results, backup
   and schema compatibility, and the expected impact of any queued approvals.

## Roll out production

1. Confirm the checkout, Docker context, Compose project and mounted
   directories. Keep the existing private bind, user/group IDs and private
   environment files. Review active attempts and pending or approved requests.
   Coordinate a maintenance window and pause the staging executor and any
   scheduled Stowarr jobs that write state. Stop the approval UI before
   taking a coordinated backup.
2. Back up both `data/media-optimizer.db` and `data/approvals.sqlite3` using
   SQLite's backup API to unique files outside the deployment directory. The
   repository's `scripts/backup-state.py` accepts `MEDIA_OPTIMIZER_DB` and
   `MEDIA_OPTIMIZER_BACKUP_DIR`. Run it once per DB with distinct protected
   destination directories. Verify the backups open, pass SQLite integrity
   checks, and contain the expected tables. Retain the previous release and
   record the backup paths privately.
3. Select the staging-tested release and check the Compose model quietly.
   From the confirmed production project, deploy the private UI alone.

   ```sh
   docker compose -f compose.yaml -f compose.approvals.yaml config --quiet
   docker compose -f compose.yaml -f compose.approvals.yaml up -d --no-deps --build stowarr-approvals
   docker compose -f compose.yaml -f compose.approvals.yaml ps --all
   docker compose -f compose.yaml -f compose.approvals.yaml logs --tail=50 stowarr-approvals
   ```

4. Confirm the UI is reachable over the existing private path, requires
   authentication, and displays the expected queue after login. Check for
   schema or permission errors and restart loops. If the release includes
   `operational_health.py`, run it with `approvals` via Compose exec.
   Keep the worker paused until the queue and staging client settings have been
   reviewed. Starting the worker may process a queued approval immediately.
5. Once cleared, start only the staging service.

   ```sh
   docker compose -f compose.yaml -f compose.approvals.yaml up -d --no-deps --build stowarr-staging
   docker compose -f compose.yaml -f compose.approvals.yaml ps --all
   docker compose -f compose.yaml -f compose.approvals.yaml logs --tail=100 stowarr-staging
   ```

   Observe worker startup and reconciliation, check for repeated errors, and
   verify Radarr and qBittorrent connectivity and category using read-only APIs
   or the `staging` operational probe if included. Allow at least one worker
   polling interval and verify attempt history remains consistent. Resume
   scheduled Stowarr jobs after verification.

## Rollback and recovery

1. On failed readiness, restart loops, migration errors or unexpected attempt
   activity, stop the staging worker first. Pause scheduled writers and stop
   the UI if database compatibility is in question. Preserve current DBs, logs
   and both release identifiers for diagnosis.
2. Revert to the recorded Compose revision and known-good images. Verify the
   previous release can read the current schema before reattaching it. Bring
   up the UI alone and repeat its verification before considering the worker.
3. If the old release cannot use the current schema, rehearse recovery from
   both backups in a separate directory with the old release. A backup can
   lose decisions recorded after it was taken. Before any approved cutover to a
   recovered database, reconcile those decisions against the preserved current
   DB, Radarr history and read-only qBittorrent observations. Keep current DBs
   archived and the worker stopped whenever there is uncertainty about whether
   an approval was already consumed or a grab was submitted.
4. Review `submitting`, `uncertain`, and historical attempts using the exact
   request and release identities. Follow the recovery lifecycle in
   [Staging approvals](approvals.md). A fresh candidate requires a new approval.
   Resume the worker and schedules only after a reviewer clears the recovered
   queue and the UI and staging checks pass. Record the final version,
   verification results, and any unresolved attempts.

This procedure scopes rollout and recovery to Stowarr. Radarr, Sonarr,
qBittorrent, Gluetun, Cloudflare/DNS, media permissions, files and torrents
require their own change procedures.
