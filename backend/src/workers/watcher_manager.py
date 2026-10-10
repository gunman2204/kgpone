"""
WatcherManager — runs dropzone_watcher in a supervised daemon thread.
Auto-restarts the thread if it crashes. Exposes is_alive() for health checks.
"""
import threading
import logging
import time

logger = logging.getLogger("watcher_manager")

class WatcherManager:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._crash_count = 0
        self._last_error: str | None = None

    def _run(self):
        """Inner loop: runs watcher, auto-restarts on crash with backoff."""
        while not self._stop_event.is_set():
            try:
                logger.info("[WatcherManager] Starting dropzone watcher thread …")
                from src.workers.dropzone_watcher import start_watcher
                start_watcher(stop_event=self._stop_event)  # blocks until crash or stop_event is set
            except Exception as e:
                self._crash_count += 1
                self._last_error = str(e)
                backoff = min(30, 5 * self._crash_count)
                logger.error(
                    f"[WatcherManager] Watcher crashed (#{self._crash_count}): {e}. "
                    f"Restarting in {backoff}s …"
                )
                if not self._stop_event.is_set():
                    time.sleep(backoff)
        logger.info("[WatcherManager] Watcher thread stopped.")

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="dropzone-watcher")
        self._thread.start()
        logger.info("[WatcherManager] Watcher thread launched.")

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            logger.info("[WatcherManager] Watcher stop signal sent. Waiting for thread to finish.")
            # Don't join indefinitely to prevent blocking main thread
            self._thread.join(timeout=3)

    def health(self) -> dict:
        alive = self._thread is not None and self._thread.is_alive()
        return {
            "status": "running" if alive else "stopped",
            "crash_count": self._crash_count,
            "last_error": self._last_error,
        }

watcher_manager = WatcherManager()
