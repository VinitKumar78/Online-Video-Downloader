"""
app/services/cleanup.py
-------------------------
Background disk cleanup.

Downloaded files accumulate on disk with every job. Without an eviction
policy, a long-running instance would eventually fill the disk. This
starts a single daemon thread that periodically removes files older than
the configured retention window.
"""

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)


def start_cleanup_thread(app) -> None:
    download_dir = app.config["DOWNLOAD_DIR"]
    retention = app.config["FILE_RETENTION_SECONDS"]
    interval = app.config["CLEANUP_INTERVAL_SECONDS"]

    def _sweep():
        while True:
            time.sleep(interval)
            try:
                _remove_expired_files(download_dir, retention)
            except Exception:  # noqa: BLE001 - a cleanup failure must not kill the thread
                logger.exception("Cleanup sweep failed")

    thread = threading.Thread(target=_sweep, daemon=True)
    thread.start()
    logger.info(
        "Cleanup thread started (retention=%ss, interval=%ss)", retention, interval
    )


def _remove_expired_files(download_dir: str, retention_seconds: int) -> None:
    now = time.time()
    if not os.path.isdir(download_dir):
        return

    for entry in os.scandir(download_dir):
        if not entry.is_file():
            continue
        age = now - entry.stat().st_mtime
        if age > retention_seconds:
            try:
                os.remove(entry.path)
                logger.info("Removed expired file: %s (age=%.0fs)", entry.name, age)
            except OSError:
                logger.warning("Could not remove expired file: %s", entry.name)
