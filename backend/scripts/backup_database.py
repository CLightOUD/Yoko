from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from backend.app.database import Database


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a consistent SQLite backup and prune old Yoko backups."
    )
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("backend/backups"),
    )
    parser.add_argument("--keep", type=int, default=14)
    args = parser.parse_args()
    if args.keep < 1:
        parser.error("--keep must be at least 1")
    return args


def main() -> int:
    args = parse_args()
    database = Database(args.database)
    database.check_readiness()
    output_dir = args.output_dir.resolve()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = output_dir / f"yoko-backup-{timestamp}.db"
    database.backup_to(target)

    backups = sorted(
        output_dir.glob("yoko-backup-*.db"),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    for old_backup in backups[args.keep :]:
        if old_backup.resolve().parent != output_dir:
            raise RuntimeError("refusing to prune a backup outside output directory")
        old_backup.unlink()
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
