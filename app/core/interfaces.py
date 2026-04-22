from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class FrameData:
    """Single video frame transferred between application layers."""

    pixels: bytes
    width: int
    height: int
    timestamp: float


class FrameProvider(ABC):
    """Abstract source of frames used by grabber and receiver code."""

    @abstractmethod
    def start(self) -> None:
        """Start producing or receiving frames."""

    @abstractmethod
    def stop(self) -> None:
        """Stop work and release resources."""

    @abstractmethod
    def get_latest_frame(self) -> FrameData:
        """Return the most recent frame."""
