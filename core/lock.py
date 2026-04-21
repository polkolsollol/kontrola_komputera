from __future__ import annotations
from abc import ABC, abstractmethod

class LockProvider(ABC):
    """Interfejs dla systemu blokady ekranu."""
    
    @abstractmethod
    def lock(self) -> None:
        """Aktywuj blokadę ekranu."""
        pass
    
    @abstractmethod
    def unlock(self) -> None:
        """Dezaktywuj blokadę ekranu."""
        pass
    
    @abstractmethod
    def is_locked(self) -> bool:
        """Sprawdź czy ekran jest zablokowany."""
        pass