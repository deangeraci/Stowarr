# Stowarr staging approvals

Optional private UI with Approve staging / Reject buttons. It stores decisions
in `data/approvals.sqlite3`, separate from completion history. No download,
import, replacement or deletion executor is enabled by this feature.

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
Import/replacement needs a separate verified approval boundary. This UI never
calls an executor and preserves existing global safety gates.

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
