from __future__ import annotations

import atexit
from typing import List

from PySide6.QtWidgets import QApplication

from .lock_window import LockWindow
from core.lock import LockProvider


class LockManager(LockProvider):
    """Zarządza oknami blokady na wszystkich podłączonych monitorach."""

    def __init__(self) -> None:
        self._lock_windows: List[LockWindow] = []
        self._locked = False

    def lock(self) -> None:
        if self._locked:
            return

        app = QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication musi istnieć przed wywołaniem lock()")

        # Tworzymy okno blokady na KAŻDYM ekranie
        for screen in app.screens():
            window = LockWindow(screen=screen)
            window.show_fullscreen()
            self._lock_windows.append(window)

        self._locked = True
        atexit.register(self.unlock)
        print("🛑 EKRAN ZABLOKOWANY")

    def unlock(self) -> None:
        if not self._locked:
            return

        for window in self._lock_windows:
            window.force_close()
        self._lock_windows.clear()
        self._locked = False
        print("🔓 EKRAN ODBLOKOWANY")

    def is_locked(self) -> bool:
        return self._locked