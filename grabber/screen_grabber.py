from __future__ import annotations

import threading
import time
from typing import Optional

import cv2
import mss
import numpy as np

from core.interfaces import FrameData, FrameProvider


class ScreenGrabber(FrameProvider):
    """Capture a monitor and store the newest frame as JPEG bytes."""

    def __init__(
        self,
        monitor_index: int = 1,
        jpeg_quality: int = 75,
        target_fps: int = 15,
    ) -> None:
        self.monitor_index = monitor_index
        self.jpeg_quality = max(1, min(jpeg_quality, 100))
        self.target_fps = max(1, target_fps)
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._latest_frame: Optional[FrameData] = None
        self._mss: Optional[mss.mss] = None

    def start(self) -> None:
        if self._running:
            return

        self._mss = mss.mss()
        monitor_count = len(self._mss.monitors)
        if self.monitor_index < 0 or self.monitor_index >= monitor_count:
            self._mss.close()
            self._mss = None
            raise ValueError(
                f"Monitor {self.monitor_index} does not exist. Available range: "
                f"0-{monitor_count - 1}"
            )

        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name="ScreenGrabber",
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

        if self._mss is not None:
            self._mss.close()
            self._mss = None

    def get_latest_frame(self) -> FrameData:
        with self._lock:
            if self._latest_frame is None:
                raise RuntimeError("No captured frame yet")
            return self._latest_frame

    def _capture_loop(self) -> None:
        assert self._mss is not None
        frame_delay = 1.0 / self.target_fps

        try:
            while self._running:
                start_time = time.perf_counter()

                screenshot = self._mss.grab(self._mss.monitors[self.monitor_index])
                frame_bgra = np.array(screenshot)
                frame_bgr = cv2.cvtColor(frame_bgra, cv2.COLOR_BGRA2BGR)
                ok, jpeg_bytes = cv2.imencode(
                    ".jpg",
                    frame_bgr,
                    [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality],
                )

                if ok:
                    frame = FrameData(
                        pixels=jpeg_bytes.tobytes(),
                        width=frame_bgr.shape[1],
                        height=frame_bgr.shape[0],
                        timestamp=time.time(),
                    )
                    with self._lock:
                        self._latest_frame = frame

                elapsed = time.perf_counter() - start_time
                sleep_time = frame_delay - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
        except Exception as exc:  # noqa: BLE001
            print(f"[ScreenGrabber] Capture loop stopped because of an error: {exc}")
            self._running = False

    def __enter__(self) -> "ScreenGrabber":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
