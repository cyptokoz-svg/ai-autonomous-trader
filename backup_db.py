#!/usr/bin/env python3
"""
Database backup script for trades.db
Run daily via cron or manually: python3 backup_db.py

Keeps the last 7 backups, deletes older ones.
"""

import shutil
import os
from datetime import datetime
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "trades.db"
BACKUP_DIR = BASE_DIR / "backups"
MAX_BACKUPS = 7


def backup_db():
    # Check source exists
    if not DB_PATH.exists():
        print(f"[ERROR] Database not found: {DB_PATH}")
        return

    # Create backups dir if needed
    BACKUP_DIR.mkdir(exist_ok=True)

    # Generate timestamped filename
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_path = BACKUP_DIR / f"trades_{timestamp}.db"

    # Copy
    shutil.copy2(DB_PATH, backup_path)
    size_mb = backup_path.stat().st_size / (1024 * 1024)
    print(f"[OK] Backup created: {backup_path.name} ({size_mb:.2f} MB)")

    # Cleanup old backups (keep last 7)
    backups = sorted(BACKUP_DIR.glob("trades_*.db"))
    if len(backups) > MAX_BACKUPS:
        to_delete = backups[: len(backups) - MAX_BACKUPS]
        for old in to_delete:
            old.unlink()
            print(f"[CLEANUP] Deleted old backup: {old.name}")

    print(f"[INFO] Total backups: {min(len(backups), MAX_BACKUPS)}")


if __name__ == "__main__":
    backup_db()
