# Stowarr

**Watch your precious cargo. Stow it smarter.**

Automatically optimize watched media to reclaim storage without sacrificing quality.

> **Status: v0.1.0-alpha / Phase 1 isolated acquisition**
>
> Stowarr currently observes media state, evaluates lifecycle eligibility,
> scores replacement candidates, and can stage approved candidates in an
> isolated qBittorrent category and path. Imports, replacements, and deletions
> are not enabled.

## What is Stowarr?

Stowarr is a lifecycle-aware storage optimizer for self-hosted media libraries
using Jellyfin, Sonarr, and Radarr.

The intended workflow is:

1. Detect when media has been watched.
2. Wait a configurable grace period.
3. Inspect the existing file and storage cost.
4. Evaluate smaller acceptable replacements.
5. Estimate potential storage savings.
6. Request approval.
7. Acquire the replacement in an isolated staging path.
8. Verify the completed media read-only.
9. Only then allow the original media to be retired.
10. Report actual storage saved.

The observation and policy layers remain read-only toward media services.
An optional private approval queue records staging decisions locally. Phase 1
never submits replacement releases through Radarr and never imports or changes
library media. See [Staging approvals](docs/approvals.md) for setup.

## Safety First

**Existing media must never be removed before its replacement has been
successfully downloaded and independently verified.**

Current safety rules include:

- Jellyfin `Played=true` determines watched state.
- Missing or uncertain completion history fails safe.
- Default watched delay is 30 days.
- Minimum replacement resolution is 1080p.
- Remux, raw-HD, BR-DISK, CAM, and telesync candidates are rejected.
- HEVC / x265 / H.265 is preferred.
- Candidates must save at least 5 GiB OR 40%.
- Source-service synchronization is read-only.
- Direct replacement downloads require explicit approval and remain isolated.
- Import, replacement, and delete capabilities remain disabled.
- Optional staging approvals pin the exact source/release and expire after 72 hours.

## Current Features

- Jellyfin watched-state inventory
- Sonarr season correlation
- Radarr movie inventory
- TV season completeness detection
- Persistent SQLite state
- Stable identity keys
- Schema versioning
- Private approval UI with Approve staging / Reject buttons
- Durable release-specific decisions and email/webhook link notifications
- Audit-log foundation
- Lifecycle safety engine
- 30-day eligibility policy
- Replacement candidate scoring
- Storage-savings calculations
- Unprivileged Docker runtime
- Secret-safe configuration
- SQLite-safe backups
- Automated validation and unit tests

## Not Yet Enabled

- Release searching
- Automatic media downloads
- Replacement imports
- Media deletion
- Telegram approval
- Automatic optimization

## Validation

Run:

    ./scripts/validate.sh

All tests and safety checks must pass before changes are committed.

## Security

Never commit API keys, passwords, tokens, or other credentials.

Runtime credentials are supplied through environment variables and local
configuration files excluded from Git.

See `SECURITY.md` for vulnerability reporting guidance.

## License

MIT
