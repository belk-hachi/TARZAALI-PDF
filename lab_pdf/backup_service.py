"""
Backup service for the Lab PDF Processor.

Uses SQLite's native hot backup API (never shutil.copy on a live DB)
to create consistent backups of:
- lab.db (via sqlite3 connection.backup())
- config.json (via shutil.copy2)
- uploads/ folder (via shutil.copytree)

Backups are stored in a backups/ directory next to the EXE, organized
by timestamp. The last N backups are kept (default 10), with older
ones automatically pruned.
"""

import os
import shutil
import sqlite3
import logging
import threading
from datetime import datetime

from .config import DB_PATH, CONFIG_FILE, UPLOAD_DIR, BACKUP_DIR, app_config

logger = logging.getLogger(__name__)

DEFAULT_MAX_BACKUPS = 10
DEFAULT_INTERVAL_SECONDS = 86400  # 24 hours (86400 seconds)


def create_backup():
    """Create a timestamped ZIP backup of the database, config, and uploads.

    Uses SQLite's hot backup API for the database to ensure consistency
    without locking or stopping the application. Everything is collected
    into a temporary directory and then compressed into a ZIP archive.

    Returns:
        The backup ZIP file path, or None on failure.
    """
    config = app_config.load()
    custom_backup_dir = config.get("backup_dir")
    effective_backup_dir = custom_backup_dir if custom_backup_dir and os.path.exists(custom_backup_dir) else BACKUP_DIR

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Base name for the ZIP (without extension)
    backup_base_name = f"backup_{timestamp}"
    # Full path to the final ZIP
    zip_path = os.path.join(effective_backup_dir, f"{backup_base_name}.zip")
    # Temporary directory for staging files
    staging_dir = os.path.join(effective_backup_dir, f"tmp_{timestamp}")

    try:
        os.makedirs(effective_backup_dir, exist_ok=True)
        os.makedirs(staging_dir, exist_ok=True)

        # 1. Backup database using SQLite hot backup API
        backup_db_path = os.path.join(staging_dir, "lab.db")
        _backup_database(backup_db_path)

        # 2. Backup config.json
        if os.path.exists(CONFIG_FILE):
            shutil.copy2(CONFIG_FILE, os.path.join(staging_dir, "config.json"))

        # 3. Backup uploads folder
        if os.path.exists(UPLOAD_DIR):
            shutil.copytree(
                UPLOAD_DIR,
                os.path.join(staging_dir, "uploads"),
                dirs_exist_ok=True,
            )

        # 4. Compress the staging directory into a ZIP
        shutil.make_archive(
            os.path.join(effective_backup_dir, backup_base_name),
            'zip',
            staging_dir
        )

        logger.info("Backup created: %s", zip_path)

        # Prune old backups
        _prune_old_backups(effective_backup_dir)

        return zip_path

    except Exception as e:
        logger.error("Backup failed: %s", e)
        return None
    finally:
        # Clean up staging directory
        if os.path.exists(staging_dir):
            try:
                shutil.rmtree(staging_dir)
            except Exception:
                pass


def _backup_database(backup_path):
    """Backup the SQLite database using the hot backup API.

    This is the ONLY safe way to copy a live SQLite database.
    Never use shutil.copy() on a database that might be in use.
    """
    src_conn = sqlite3.connect(DB_PATH)
    try:
        dst_conn = sqlite3.connect(backup_path)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()


def _prune_old_backups(backup_dir):
    """Remove old backups beyond the configured maximum.

    Reads max_backups from config, falls back to DEFAULT_MAX_BACKUPS.
    Backups (both folders and ZIPs) are sorted by name and the
    oldest are deleted first.
    """
    config = app_config.load()
    max_backups = config.get("max_backups", DEFAULT_MAX_BACKUPS)

    if not os.path.exists(backup_dir):
        return

    # List backup files/dirs sorted by name (=timestamp) ascending
    backups = sorted(
        d for d in os.listdir(backup_dir)
        if d.startswith("backup_") and (
            os.path.isdir(os.path.join(backup_dir, d)) or
            d.endswith(".zip")
        )
    )

    # Delete oldest backups beyond the limit
    while len(backups) > max_backups:
        old_item = os.path.join(backup_dir, backups.pop(0))
        try:
            if os.path.isdir(old_item):
                shutil.rmtree(old_item)
            else:
                os.remove(old_item)
            logger.info("Pruned old backup: %s", old_item)
        except Exception as e:
            logger.error("Failed to prune backup %s: %s", old_item, e)


class BackupScheduler:
    """Simple background thread that creates periodic backups.

    Uses threading.Timer instead of a full scheduler framework,
    appropriate for a single-user desktop application.
    """

    def __init__(self, interval=DEFAULT_INTERVAL_SECONDS):
        self._interval = interval
        self._timer = None
        self._running = False

    def start(self):
        """Start the periodic backup scheduler."""
        if self._running:
            return
        self._running = True
        self._schedule_next()
        logger.info(
            "Backup scheduler started (interval: %ds)", self._interval
        )

    def stop(self):
        """Stop the periodic backup scheduler."""
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        logger.info("Backup scheduler stopped")

    def _schedule_next(self):
        if not self._running:
            return
        self._timer = threading.Timer(self._interval, self._run_backup)
        self._timer.daemon = True
        self._timer.start()

    def _run_backup(self):
        try:
            create_backup()
        except Exception as e:
            logger.error("Scheduled backup failed: %s", e)
        finally:
            self._schedule_next()


# Module-level singleton
backup_scheduler = BackupScheduler()
