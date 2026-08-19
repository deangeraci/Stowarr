# Media Optimizer

Automated archival-quality optimization for self-hosted media libraries.

Initial target workflow:

Jellyfin watched state
  -> grace period
  -> inspect current Sonarr/Radarr media
  -> search candidate releases
  -> compare quality/size/codec
  -> estimate storage savings
  -> approval or automatic replacement
  -> verify successful import
  -> preserve original on failure
  -> report actual savings

## Safety invariant

The existing media file must never be deleted before the replacement has
successfully downloaded, imported, and been verified.

## v0.1

READ-ONLY ONLY.

- Jellyfin integration
- Sonarr integration
- Radarr integration
- library inventory
- watched-state analysis
- candidate scoring
- estimated savings
- no downloads
- no deletion
- no media modification
## Safety Architecture

Media Optimizer is designed around strict separation between observation,
eligibility, approval, acquisition, and replacement.

Current safety rules:

- Jellyfin `Played=true` determines watched state.
- A completed item without trustworthy completion timing is blocked.
- Historical incomplete playback evidence is never converted into an automatic completion date.
- Default watched delay is 30 days.
- Replacement candidates must be at least 1080p.
- Remux, raw-HD, BR-DISK, CAM, and telesync candidates are rejected.
- HEVC/x265/H.265 is preferred.
- A candidate must save at least 5 GiB OR 40 percent.
- Source-service synchronization is read-only.
- Download, import, and delete capabilities remain disabled.
- Original media must never be removed before a replacement has been successfully imported and verified.
- Initial production workflow requires explicit user approval.

## Current Development State

Implemented:

- Dockerized application
- unprivileged runtime
- Docker secret/build-context hygiene
- Jellyfin connectivity
- Sonarr connectivity
- Radarr connectivity
- Jellyfin watched-state inventory
- TV season completeness
- movie inventory
- persistent SQLite state
- stable identity keys
- schema versioning
- audit-log schema
- lifecycle safety engine
- 30-day eligibility rules
- replacement candidate policy
- unit tests
- one-command validation
- SQLite-safe backup utility

Not yet enabled:

- release searching
- downloading
- importing
- deleting/replacing media
- Telegram approval
- automatic optimization

Those capabilities must remain disabled until the read-only lifecycle and
candidate-selection pipeline has been validated.
