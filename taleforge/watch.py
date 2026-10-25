"""Hot-reload: observa arquivos com watchdog (ou faz polling se não estiver instalado)."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

log = logging.getLogger("taleforge.watch")


class Watcher:
    def __init__(self, paths: list[Path], callback: Callable[[Path], None], interval: float = 0.5):
        self.paths = [p for p in paths if p.exists()]
        self.callback = callback
        self.interval = interval
        self._observer = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer

            cb = self.callback

            class _Handler(FileSystemEventHandler):
                def on_any_event(self, event):  # noqa: D401
                    if not event.is_directory and event.event_type in ("modified", "created", "moved", "deleted"):
                        cb(Path(getattr(event, "dest_path", "") or event.src_path))

            self._observer = Observer()
            for p in self.paths:
                self._observer.schedule(_Handler(), str(p if p.is_dir() else p.parent), recursive=p.is_dir())
            self._observer.daemon = True
            self._observer.start()
        except Exception as exc:  # watchdog ausente ou inotify indisponível
            log.info("watchdog indisponível (%s); usando polling", exc)
            self._observer = None
            self._thread = threading.Thread(target=self._poll, name="taleforge-watch", daemon=True)
            self._thread.start()

    def _snapshot(self) -> dict[Path, float]:
        snap: dict[Path, float] = {}
        for base in self.paths:
            files = base.rglob("*") if base.is_dir() else [base]
            for f in files:
                try:
                    if f.is_file():
                        snap[f] = f.stat().st_mtime
                except OSError:
                    pass
        return snap

    def _poll(self) -> None:
        prev = self._snapshot()
        while not self._stop.wait(self.interval):
            cur = self._snapshot()
            for f in set(prev) | set(cur):
                if prev.get(f) != cur.get(f):
                    self.callback(f)
            prev = cur

    def stop(self) -> None:
        self._stop.set()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=1)
