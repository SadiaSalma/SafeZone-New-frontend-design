"""
jobs.py - small background jobs that run inside the backend (Task 22).

AlertWorker: a helper thread that sends queued alerts. It checks every few seconds,
and wake() makes it check RIGHT NOW (called after a verifier approves a report).
So an alert normally leaves within a second or two of approval.

It starts with the server (see main.py "lifespan") and stops with it.
Tests switch it off (BACKGROUND_JOBS=false in tests/conftest.py) and call run_once() themselves.
"""
import threading

from app.config import settings


class AlertWorker:
    def __init__(self, every_seconds: float = 5.0):
        self.every_seconds = every_seconds
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="safezone-alert-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)

    def wake(self) -> None:
        self._wake.set()

    def _loop(self) -> None:
        import time

        from app.modules.alerts.sender import run_once  # imported here so the database is ready first
        from app.modules.ocr.service import purge

        last_purge = 0.0
        while not self._stop.is_set():
            try:
                run_once()
                if time.monotonic() - last_purge > 600:  # Task 29 / R8: delete GD scans whose time is up
                    purge()
                    last_purge = time.monotonic()
            except Exception as error:  # noqa: BLE001 - the worker must never die (e.g. database restarting)
                print(f"[alert worker] {type(error).__name__}: {error}", flush=True)
            self._wake.wait(timeout=self.every_seconds)
            self._wake.clear()


alert_worker = AlertWorker()


def wake_alert_worker() -> None:
    """Send waiting alerts now (if the worker runs in this process)."""
    if settings.background_jobs:
        alert_worker.wake()
