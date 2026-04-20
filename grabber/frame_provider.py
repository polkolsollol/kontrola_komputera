from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class FrameData:
    """Obiekt transferowy, który będzie krążył wewnątrz aplikacji."""
    pixels: bytes
    width: int
    height: int
    timestamp: float


class FrameProvider(ABC):
    """Abstrakcyjny interfejs dostawcy klatek."""

    @abstractmethod
    def start(self):
        """Uruchamia proces przechwytywania."""
        pass

    @abstractmethod
    def stop(self):
        """Zatrzymuje proces i zwalnia zasoby."""
        pass

    @abstractmethod
    def get_latest_frame(self) -> FrameData:
        """Zwraca ostatnią przechwyconą klatkę w ustandaryzowanym formacie."""
        pass


