import threading
import time
import cv2
import numpy as np
import mss

from frame_provider import FrameProvider, FrameData


class ScreenGrabber(FrameProvider):
    """
    Klasa przechwytująca ekran za pomocą mss i kompresująca JPEG za pomocą OpenCV.
    Działa w wątku w tle, zapewniając ciągły strumień klatek.
    """

    def __init__(self, monitor_index: int = 1, jpeg_quality: int = 75):
        """
        Args:
            monitor_index: Indeks monitora do przechwytywania (1 = główny)
            jpeg_quality: Jakość kompresji JPEG (0-100, domyślnie 75)
        """
        self.monitor_index = monitor_index
        self.jpeg_quality = jpeg_quality
        self._thread = None
        self._running = False
        self._lock = threading.Lock()
        self._latest_frame = None
        self._mss = mss.mss()

    def start(self):
        """Uruchamia wątek przechwytywania w tle."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        print(f"[ScreenGrabber] Gestartet - monitor {self.monitor_index}")

    def stop(self):
        """Zatrzymuje przechwytywanie i zwalnia zasoby."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        self._mss.close()
        print("[ScreenGrabber] Zatrzymany")

        def get_latest_frame(self) -> FrameData:
        """
        Zwraca ostatnią przechwyconą klatkę lub None jeśli żadna nie dostępna.
        """
        with self._lock:
            if self._latest_frame is None:
                raise RuntimeError("Brak dostępnych klatek - upewnij się, że start() został wywołany")
            return self._latest_frame