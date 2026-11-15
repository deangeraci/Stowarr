# Operational health checks

Run these from the intended Compose checkout after the services are already
running. Check that the intended services are running and their restart counts
are stable before treating a successful probe as a rollout signal.

```sh
docker compose -f compose.yaml -f compose.approvals.yaml ps --all
docker compose -f compose.yaml -f compose.approvals.yaml exec -T stowarr-approvals \
  python /app/src/operational_health.py approvals
docker compose -f compose.yaml -f compose.approvals.yaml exec -T stowarr-staging \
  python /app/src/operational_health.py staging
```

The approvals probe checks SQLite and the authenticated local UI. The staging
probe checks both databases, the configured Stowarr safety gates and executor
identity, the enabled Radarr qBittorrent client and its movie category, and the
presence of that category in qBittorrent. Compare the Radarr client's configured
destination to the intended qBittorrent instance during rollout if your network
has aliases or multiple instances. Check staging logs for worker and reconciliation
progress because the worker has no HTTP listener.

The checks use SQLite read-only connections and never initialize or migrate a
database. When checking databases configured for WAL, use consistent SQLite
backups created separately or run with the database directory mounted read-only
to prevent SQLite from creating shared-memory sidecars. The service APIs are read
with GET, apart from qBittorrent session login when credentials are configured.
No worker, approval decision, or torrent/media action is invoked. Results are
redacted and any failed check exits with status 1.

Use `--help` for path overrides when deployments use nondefault paths.
