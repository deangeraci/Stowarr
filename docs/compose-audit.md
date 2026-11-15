# Compose health and restart policy audit

| Service | Recommendation | Reason |
| --- | --- | --- |
| `stowarr-approvals` | Add a local HTTP healthcheck and retain `unless-stopped`. | The UI is a long-running service. An unauthenticated request should return 401 after the server starts. The probe requires no credentials, changes no state, and runs inside the container. |
| `stowarr-staging` | Retain `unless-stopped` and monitor logs and restart counts. | The executor has no HTTP listener. A process check would duplicate container state, and a Radarr or qBittorrent outage should not serve as a reason to restart the executor. |
| `media-optimizer` | Retain `restart: "no"` without a healthcheck. | This service is used for one-shot operations. Restarting it could repeat a run and a periodic probe adds little value. |

An unhealthy approvals status reports HTTP availability only. Verify the
database and authenticated queue separately during rollout. Docker Compose
does not automatically restart a container when its health status changes.
