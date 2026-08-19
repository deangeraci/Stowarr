from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path


SOURCE = Path(
    os.environ.get(
        "MEDIA_OPTIMIZER_DB",
        "data/media-optimizer.db",
    )
)

DEST_ROOT = Path(
    os.environ.get(
        "MEDIA_OPTIMIZER_BACKUP_DIR",
        "backups",
    )
)


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(
            f"Database not found: {SOURCE}"
        )

    stamp = datetime.now().strftime(
        "%Y%m%d-%H%M%S"
    )

    destination = (
        DEST_ROOT
        / f"state-{stamp}.db"
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    source = sqlite3.connect(SOURCE)
    target = sqlite3.connect(destination)

    try:
        source.backup(target)
    finally:
        target.close()
        source.close()

    print(destination)


if __name__ == "__main__":
    main()
