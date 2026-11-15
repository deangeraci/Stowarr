# Stowarr staging approvals

Optional private UI with Approve staging / Reject buttons. It stores decisions
in `data/approvals.sqlite3`, separate from completion history. The staging
service can acquire an approved exact release into an isolated qBittorrent
category and path. Importing, replacement, and deletion remain separate
workflows.

## Install

From your existing Stowarr checkout, after applying the feature branch:

```sh
umask 077
python3 - <<'PY'
from pathlib import Path
import secrets
p = Path('.env.approvals')
with p.open('x') as f:
    f.write('STOWARR_APPROVAL_USER=stowarr\n')
    f.write('STOWARR_APPROVAL_PASSWORD=' + secrets.token_urlsafe(32) + '\n')
PY
# Keep PUID/PGID consistent with the existing data directory ownership.
docker compose -f compose.yaml -f compose.approvals.yaml up -d --build stowarr-approvals
```

Default access: NAS loopback port 8787. Use an SSH tunnel or a private HTTPS
reverse proxy. For a tunnel from your PC:

```sh
ssh -N -L 8787:127.0.0.1:8787 'Dean Geraci@192.168.1.83'
```

Open `http://127.0.0.1:8787` on that PC. Username is `stowarr`; retrieve the
password locally from `.env.approvals`. Do not paste it into chat. Basic auth
requires HTTPS or an encrypted SSH/Tailscale path for remote access. Avoid a
public port forward. The password is an instance administrator credential;
this MVP has no per-user accounts or per-user notification preferences.

## Create requests

Proposals must come from a live, policy-eligible candidate and include exactly
these fields (identifiers are strings; sizes are integer bytes):

```json
{
  "identity_key": "movie:tmdb:315635",
  "title": "Spider-Man: Homecoming (2017)",
  "source_file_id": "current-radarr-movie-file-id",
  "source_size_bytes": 20766100000,
  "release_id": "exact-release-infohash-or-opaque-id",
  "release_title": "exact-selected-release-title",
  "release_size_bytes": 6292120000,
  "indexer_id": "selected-indexer-id"
}
```

These are illustrative values, not a verified Homecoming proposal. The existing
Homecoming staging download is already approved; do not enqueue it again.
No download URLs, magnets, tokens or API keys belong in proposal fields.

For a sanitized `proposal.json` on the NAS:

```sh
docker compose -f compose.yaml -f compose.approvals.yaml exec -T stowarr-approvals \
  python /app/src/approvals.py propose /dev/stdin --ttl-hours 72 < proposal.json
```

This feature adds the queue interface; the existing candidate evaluator does
not automatically submit requests yet. Future integration should call
`ApprovalStore.propose(snapshot)` only after eligibility/policy checks.
Duplicates of active proposals reuse the existing request. Approval and
rejection are audited. Decisions cannot be edited or replayed. After expiry,
re-evaluate the live candidate before creating a fresh request.

## Notification preferences

Web buttons always work without an external provider. For link notifications,
copy optional variables from `.env.approvals.example` into `.env.approvals`:

- `STOWARR_NOTIFY_CHANNELS=email`: SMTP with mandatory STARTTLS.
- `STOWARR_NOTIFY_CHANNELS=webhook`: HTTPS JSON POST, optional bearer token.
- `STOWARR_NOTIFY_CHANNELS=email,webhook`: both.
- Empty: web page only.

Set `STOWARR_APPROVAL_URL` to the private origin users can reach. Add `--notify`
to the proposal command. Notifications link to the authenticated request page;
opening a link never approves anything. Delivery failure leaves the request
queued. Notifications are sent by the CLI, not the web service. Retry manually
with the same proposal and `--notify`; this reuses the request but can resend.
No automatic notification retry worker is included.

The generic webhook payload contains `event`, `request_id`, `title`,
`release_title`, `savings_bytes` and `approval_url`. An adapter can convert it
into Telegram, ntfy, Discord, Home Assistant or other messages. Native provider
buttons, SMS, and inbound webhook approvals are not implemented in this MVP.
Notification destinations are administrator-controlled; messages reveal titles.

## Executor contract

Approvals cover **staging only**, not replacement. A future executor must fetch
live watch/household eligibility, grace period, release availability and source
file state; reject uncertain or changed data; reconstruct the exact snapshot;
then atomically call `store.consume(request_id, current_snapshot)` before
staging. The hash pins source file ID/size, release ID/title/size, indexer and
media identity. Any changed field invalidates authorization. `consume` is an
at-most-once claim, not download success. Reconcile errors before a new request.
The optional staging service rechecks live completion, Played status, the current
source file and exact release availability before direct qBittorrent acquisition.
It never imports, replaces, or deletes library media.

Back up approvals with SQLite's backup API alongside completion state. Changing
the password requires recreating the service. All request mutations require
an authenticated POST and a session CSRF token; no GET endpoint changes state.

## Queue a live movie candidate

`movie_approvals.py` queues one proposal for an explicitly selected Radarr movie
and Jellyfin user. It reads trusted completion state, recomputes the configured
grace period, confirms live Jellyfin Played status, matches provider IDs, then
searches Radarr and pins the current imported file ID/size and release hash.
Only existing-cutoff rejections are tolerated. A matching release needs reported
seeders, 1080p HEVC, an infohash/indexer ID and acceptable base savings.

```sh
docker compose -f compose.yaml -f compose.approvals.yaml run --rm -T \
  --entrypoint python media-optimizer /app/src/movie_approvals.py \
  --movie-id RADARR_ID --user-id JELLYFIN_USER_ID
```

The first phase uses an explicit operator-selected movie; it does not schedule
whole-library scans or execute downloads. This is one user's staging eligibility,
not household replacement clearance. Default candidate package size is 4–8 GiB;
set `approvals.minimum_candidate_gib` and `approvals.maximum_candidate_gib` in
local configuration to customize it. The highest reported-seeder qualifying
release is proposed; all release metadata still needs post-download verification.
`--notify` uses the same optional environment-based notification adapters; configure
those variables in the command's service environment before using it.

## Execute approved staging

Set `STOWARR_EXECUTOR_JELLYFIN_USER_ID` in `.env.approvals` to the eligible
32-character Jellyfin user ID, then start `stowarr-staging` alongside the UI.
It checks approved requests every minute and consumes one only after the same
live eligibility and exact-release checks pass. Radarr client ID 2 remains the
normal monitored client and category. Phase 1 uses the separate
`STOWARR_REPLACEMENT_CATEGORY` and `STOWARR_REPLACEMENT_PATH` values for direct
qBittorrent acquisition. If qBittorrent requires authentication, set the
username/password in the private `.env.approvals` file; the client logs in for
a session cookie and never logs or exposes those values. It never imports,
replaces, moves, or deletes media and does not call a Radarr submission or
import endpoint.

### Recovery lifecycle

Every consumed approval has one durable staging attempt. The claim and attempt
row are committed in one SQLite transaction, so a restart or concurrent worker
cannot claim the approval twice. A submission timeout, 5xx, or 429 is recorded
as `uncertain`; a deterministic qBittorrent 4xx is `failed`. Neither is retried.

Reconciliation runs before processing new approvals. Legacy attempts may read
Radarr history, while Phase 1 attempts read qBittorrent's read-only
`torrents/info` endpoint in the isolated category. It records these observations:

- `grabbed`/`imported`: legacy Radarr history evidence;
- `downloading` or `stalled`: the exact hash still exists in its recorded category;
- `complete_unverified`: an isolated torrent is complete but awaits media verification;
- `failed`: the service reported a failed download;
- `missing`: the exact categorized torrent is gone;
- `ambiguous`: evidence is incomplete or a service is unavailable.

An ambiguous result is logged and left for the next reconciliation. A missing
release re-runs live eligibility and Radarr candidate discovery, pins the
currently best qualifying candidate, and creates exactly one new pending
approval linked to the old attempt; an operator must review it before any new
grab. Recovery approvals retain a durable parent link, and every release hash
in that lineage is excluded, so a later recovery cannot cycle back to an older
release (A → B cannot later select A). If no new qualifying release remains,
the attempt stays missing/unresolved for later reconciliation. The old
approval remains consumed, and stale release snapshots are never cloned.
The executor never removes torrents, pauses/resumes them, deletes files, or
automatically retries a grab.

## Phase 1 isolated acquisition

Phase 1 downloads approved replacement candidates directly through qBittorrent.
It does not submit them to Radarr's `/api/v3/release` endpoint. Set
`STOWARR_REPLACEMENT_CATEGORY` to a pre-created qBittorrent category that is
different from Radarr's monitored `STOWARR_QBITTORRENT_CATEGORY`, and set
`STOWARR_REPLACEMENT_PATH` to an absolute path visible identically to the
qBittorrent and Stowarr containers. The path must be outside every Radarr root
folder. The executor enumerates every enabled Radarr download client and rejects
any client using the replacement category. It also requires qBittorrent's
category `savePath` to resolve to the same staging path, resolves filesystem
symlinks before overlap checks, and accepts `STOWARR_RADARR_ROOT_PATH_MAP` only
as an explicit mapping for Radarr container paths that differ from Stowarr's.
Startup fails closed when any root, mapping, category, save path, or shared path
cannot be verified.

The direct submission uses the exact release URL returned by the live Radarr
release search only as a source for qBittorrent. It never sends the release
back to Radarr, and it never calls an import, rename, delete, or replacement
endpoint. The dedicated category and path keep Completed Download Handling
from observing the replacement download. qBittorrent 5.2.x login responses
with HTTP 204 and a `QBT_SID_<port>` cookie are supported alongside legacy
HTTP 200 `Ok.` responses.

Completed downloads remain in `complete_unverified` until the read-only
`staging_verification.py` command confirms the qBittorrent hash/category/path,
file size, ffprobe metadata, SHA-256 digest, and a full ffmpeg video decode.
Verification only records a manifest. FFmpeg is restricted to one worker thread,
each job has a bounded timeout and 32 GiB file-size ceiling, and the CLI caps
concurrent verification jobs at four (`STOWARR_VERIFY_WORKERS`). Phase 1 has no
media swap, deletion, quarantine cleanup, or Radarr quality-profile mutation.

Run verification for the isolated staging service with:

```sh
docker compose -f compose.yaml -f compose.approvals.yaml exec -T stowarr-staging \
  python /app/src/staging_verification.py
```

Existing pending or approved requests created by the pre-Phase-1 executor are
not reinterpreted automatically. Review them first with:

```sh
docker compose -f compose.yaml -f compose.approvals.yaml run --rm -T \
  --entrypoint python media-optimizer /app/src/approvals.py \
  --db /app/data/approvals.sqlite3 migrate-phase1
```

Only after a separately authorized review should the operator repeat the command
with `--authorize --actor NAME`. That explicit action marks the reviewed rows
`direct-qbit-v1` and records a `phase1_migrated` audit event. Their request IDs,
snapshots, decisions, and recovery lineage remain unchanged. Migration consumes
no approval and submits no torrent. Until then, legacy pending/approved rows
remain deferred.

On startup, the schema migration backfills consumed approvals that predate the
staging table as historical attempts. This is intentionally read-only and lets
the four consumed approvals from October 8 be reconciled against current Radarr
history/qBittorrent state without replaying them. Backups should be taken before
upgrading, and the service should be monitored for `staging_reconciled`,
`staging_missing`, and `Staging reconciliation failed` log lines.

Existing 4K media is preserved: this workflow only stages an approved smaller
candidate and does not run Radarr import or replacement operations. Keep
Cleanuparr deletion disabled in production.
