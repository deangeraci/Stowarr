# Stowarr

**Watch your precious cargo. Stow it smarter.**

Automatically optimize watched media to reclaim storage without sacrificing quality.

> **Status: v0.1.0-alpha / read-only**
>
> Stowarr currently observes media state, evaluates lifecycle eligibility,
> and scores replacement candidates. Downloads, imports, replacements,
> and deletions are not yet enabled.

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
7. Acquire the replacement through Sonarr or Radarr.
8. Verify the successful import.
9. Only then allow the original media to be retired.
10. Report actual storage saved.

Only the read-only observation and policy layers are implemented today.

## Safety First

**Existing media must never be removed before its replacement has been
successfully downloaded, imported, and verified.**

Current safety rules include:

- Jellyfin `Played=true` determines watched state.
- Missing or uncertain completion history fails safe.
- Default watched delay is 30 days.
- Minimum replacement resolution is 1080p.
- Remux, raw-HD, BR-DISK, CAM, and telesync candidates are rejected.
- HEVC / x265 / H.265 is preferred.
- Candidates must save at least 5 GiB OR 40%.
- Source-service synchronization is read-only.
- Download, import, and delete capabilities remain disabled.
- Initial write-enabled workflows will require explicit approval.

## Current Features

- Jellyfin watched-state inventory
- Sonarr season correlation
- Radarr movie inventory
- TV season completeness detection
- Persistent SQLite state
- Stable identity keys
- Schema versioning
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
- Downloads
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
