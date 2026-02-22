"""
kappman.watcher
===============
Background folder watcher using the ``watchdog`` library.

The :class:`AppImageWatcher` class owns an :class:`~watchdog.observers.Observer`
and exposes a clean :meth:`~AppImageWatcher.stop` mechanism via
:class:`threading.Event`.  This makes it safe to call ``stop()`` from any
thread (including the Qt GUI thread) without risking a deadlock.

:class:`AppImageEventHandler` translates filesystem events into calls to
:func:`~kappman.core.integrate_appimage` and
:func:`~kappman.core.remove_appimage`.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileMovedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from kappman.core import integrate_appimage, remove_appimage
from kappman.config import get_watch_dir

logger = logging.getLogger(__name__)


class AppImageEventHandler(FileSystemEventHandler):
    """Watchdog event handler that reacts to ``.AppImage`` filesystem events.

    Created events trigger :func:`~kappman.core.integrate_appimage`.
    Deleted events trigger :func:`~kappman.core.remove_appimage`.
    Moved events are decomposed into a deletion of the old path and a
    creation of the new path.
    """

    @staticmethod
    def _is_appimage(path: str) -> bool:
        return path.lower().endswith(".appimage")

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory or not self._is_appimage(event.src_path):
            return
        logger.info("New AppImage detected: %s", event.src_path)
        try:
            result = integrate_appimage(event.src_path)
            logger.info("Integrated: %s", result["app_name"])
        except Exception:
            logger.exception("Integration failed for %s", event.src_path)

    def on_deleted(self, event: FileDeletedEvent) -> None:
        if event.is_directory or not self._is_appimage(event.src_path):
            return
        logger.info("AppImage removed from watch dir: %s", event.src_path)
        removed = remove_appimage(event.src_path)
        if removed:
            logger.info("Removed desktop entry for: %s", Path(event.src_path).stem)

    def on_moved(self, event: FileMovedEvent) -> None:
        """Treat a move as a deletion + creation so the desktop entry stays in sync."""
        if event.is_directory:
            return
        if self._is_appimage(event.src_path):
            self.on_deleted(FileDeletedEvent(event.src_path))
        if self._is_appimage(event.dest_path):
            self.on_created(FileCreatedEvent(event.dest_path))


class AppImageWatcher:
    """Manages the lifecycle of a :class:`~watchdog.observers.Observer`.

    Attributes
    ----------
    watch_dir:
        The directory being monitored.

    Notes
    -----
    :meth:`run_forever` blocks on :attr:`_stop_event` via ``Event.wait()``.
    This means :meth:`stop` can be called from any thread and will unblock
    ``run_forever`` immediately — no polling loop, no deadlock.
    """

    def __init__(self, watch_dir: Path | str | None = None) -> None:
        self.watch_dir = Path(watch_dir or get_watch_dir()).expanduser()
        self._observer: Observer | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Create the watch directory if needed, then start the observer."""
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self._stop_event.clear()
        handler = AppImageEventHandler()
        self._observer = Observer()
        self._observer.schedule(handler, str(self.watch_dir), recursive=False)
        self._observer.start()
        logger.info("Watching %s for AppImages", self.watch_dir)

    def stop(self) -> None:
        """Signal the watcher to stop.

        Sets the stop event (which unblocks :meth:`run_forever`) and then
        shuts down the observer.  Safe to call from any thread.
        """
        self._stop_event.set()
        if self._observer and self._observer.is_alive():
            self._observer.stop()
            self._observer.join()
            logger.info("Watcher stopped")

    def run_forever(self) -> None:
        """Start watching and block until :meth:`stop` is called.

        Uses :meth:`threading.Event.wait` instead of a polling ``sleep``
        loop so that :meth:`stop` can wake this method immediately.
        """
        self.start()
        try:
            self._stop_event.wait()
        finally:
            if self._observer and self._observer.is_alive():
                self._observer.stop()
                self._observer.join()
