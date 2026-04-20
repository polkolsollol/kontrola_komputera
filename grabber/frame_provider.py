from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class FrameData:
    """Obiekt transferowy, który będzie krążył wewnątrz aplikacji."""
    pixels: bytes
    width: int
    height: int
    timestamp: floa