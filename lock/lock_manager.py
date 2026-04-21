from __future__ import annotations
from typing import List
import atexit
from PySide6.QtWidgets import QApplication
from .lock_window import LockWindow
from core.lock import LockProvider

class LockManager(LockProvider):
    def __init__(self):
        self._lock_windows: List[LockWindow] = []
        self._locked = False
    
    def lock(self) -> None:
        if self._locked:
            return
        
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        
        window = LockWindow()
        window.show_fullscreen()
        self._lock_windows.append(window)
        self._locked = True
        atexit.register(self.unlock)
        print("🛑 EKRAN ZABLOKOWANY")
    
    def unlock(self) -> None:
        for window in self._lock_windows:
            window.close()
        self._lock_windows.clear()
        self._locked = False
        print("🔓 EKRAN ODBLOKOWANY")
    
    def is_locked(self) -> bool:
        return self._locked