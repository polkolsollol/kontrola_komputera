"""
ui/ui.py – Warstwa interfejsu użytkownika (PySide6) dla aplikacji zdalnego podglądu ekranu.

Architektura
────────────
MainWindow – Główne okno aplikacji.
NetworkFrameProvider – adapter do NetworkReceiver (odbiera JPEG w tle).
FrameWorker – wątek Qt pobierający klatki i dekodujący JPEG przez QImage.loadFromData().
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from PySide6.QtCore import (
    QObject,
    QThread,
    QTimer,
    Signal,
    Slot,
    Qt,
    QRect,
    QPoint,
)
from PySide6.QtGui import (
    QImage,
    QPixmap,
    QPainter,
    QColor,
    QFont,
    QPen,
    QBrush,
    QLinearGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QStatusBar,
    QSizePolicy,
    QFrame,
)

import sys

from core.interfaces import FrameData, FrameProvider
from network.connection import NetworkReceiver

_JPEG_SOI = b"\xff\xd8"


# ═══════════════════════════════════════════════
# 1. NetworkFrameProvider
# ═══════════════════════════════════════════════
class NetworkFrameProvider(FrameProvider):
    def __init__(self, host: str, port: int = 9000) -> None:
        self._receiver = NetworkReceiver(host=host, port=port)
        self._thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._lock = threading.Lock()
        self._latest_frame: Optional[FrameData] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._receive_loop, daemon=True, name="NetworkFrameProvider"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._receiver.socket is not None:
            try:
                self._receiver.socket.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def get_latest_frame(self) -> FrameData:
        with self._lock:
            if self._latest_frame is None:
                raise RuntimeError("Brak klatek – oczekiwanie na połączenie")
            return self._latest_frame

    def _receive_loop(self) -> None:
        try:
            self._receiver.connect()
        except Exception as exc:
            print(f"[NetworkFrameProvider] Nie udało się połączyć: {exc}")
            return

        while self._running:
            try:
                frame = self._receiver.receive_frame()
                with self._lock:
                    self._latest_frame = frame
            except (ConnectionError, OSError):
                if self._running:
                    print("[NetworkFrameProvider] Utracono połączenie, ponawiam…")
                    try:
                        self._receiver.connect()
                    except Exception:
                        break
            except Exception as exc:
                if self._running:
                    print(f"[NetworkFrameProvider] Błąd: {exc}")
            time.sleep(0.01)


# ═══════════════════════════════════════════════
# 2. FrameWorker
# ═══════════════════════════════════════════════
class FrameWorker(QObject):
    frame_ready = Signal(QImage)
    fps_updated = Signal(float)

    DEFAULT_INTERVAL_MS = 33

    def __init__(self, provider: FrameProvider, interval_ms: int = DEFAULT_INTERVAL_MS) -> None:
        super().__init__()
        self._provider = provider
        self._interval_ms = interval_ms
        self._running = False
        self._timer: Optional[QTimer] = None
        self._fps_frame_count = 0
        self._fps_last_time = time.time()

    @Slot()
    def start_loop(self) -> None:
        self._running = True
        self._provider.start()
        self._timer = QTimer()
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self._interval_ms)

    @Slot()
    def stop_loop(self) -> None:
        self._running = False
        if self._timer is not None:
            self._timer.stop()
        self._provider.stop()

    def _tick(self) -> None:
        if not self._running:
            return
        try:
            frame_data = self._provider.get_latest_frame()
        except RuntimeError:
            return

        qimg = self._frame_data_to_qimage(frame_data)
        if qimg.isNull():
            return

        self.frame_ready.emit(qimg)

        self._fps_frame_count += 1
        now = time.time()
        elapsed = now - self._fps_last_time
        if elapsed >= 1.0:
            fps = self._fps_frame_count / elapsed
            self.fps_updated.emit(fps)
            self._fps_frame_count = 0
            self._fps_last_time = now

    @staticmethod
    def _frame_data_to_qimage(fd: FrameData) -> QImage:
        img = QImage()
        if img.loadFromData(fd.pixels):
            return img
        return QImage()


# ═══════════════════════════════════════════════
# 3. VideoWidget + MainWindow
# ═══════════════════════════════════════════════
class VideoWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background-color: #1e1e2e;")

    @Slot(QImage)
    def update_frame(self, image: QImage) -> None:
        self._pixmap = QPixmap.fromImage(image)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.setPen(QColor(120, 120, 140))
            painter.setFont(QFont("Sans", 16))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Brak strumienia wideo\nPodaj IP i kliknij Połącz",
            )
        painter.end()


class MainWindow(QMainWindow):
    DEFAULT_PORT = 9000

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Zdalny Podgląd Ekranu")
        self.resize(960, 640)
        self._connected = False
        self._frame_provider: Optional[FrameProvider] = None
        self._worker: Optional[FrameWorker] = None
        self._worker_thread: Optional[QThread] = None
        self._build_ui()
        self._apply_styles()

    def _build_ui(self) -> None:
        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("toolbar")
        toolbar_layout = QHBoxLayout(toolbar_frame)
        toolbar_layout.setContentsMargins(12, 8, 12, 8)

        lbl_ip = QLabel("Adres IP serwera:")
        lbl_ip.setStyleSheet("color: #cdd6f4; font-weight: bold;")
        self._ip_input = QLineEdit()
        self._ip_input.setPlaceholderText("np. 192.168.1.100")
        self._ip_input.setFixedWidth(260)
        self._ip_input.setStyleSheet(
            "QLineEdit { background: #313244; color: #cdd6f4; border: 1px solid #585b70;"
            " border-radius: 4px; padding: 4px 8px; }"
            "QLineEdit:focus { border-color: #89b4fa; }"
        )

        self._btn_connect = QPushButton("Połącz")
        self._btn_connect.setFixedWidth(130)
        self._btn_connect.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_connect.clicked.connect(self._toggle_connection)

        toolbar_layout.addWidget(lbl_ip)
        toolbar_layout.addWidget(self._ip_input)
        toolbar_layout.addSpacing(8)
        toolbar_layout.addWidget(self._btn_connect)
        toolbar_layout.addStretch()

        self._video_widget = VideoWidget()

        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(toolbar_frame)
        main_layout.addWidget(self._video_widget, stretch=1)
        self.setCentralWidget(central)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_label = QLabel("Stan: Rozłączono")
        self._fps_label = QLabel("FPS: –")
        self._status_bar.addWidget(self._status_label, stretch=1)
        self._status_bar.addPermanentWidget(self._fps_label)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background-color: #1e1e2e; }
            #toolbar { background-color: #181825; border-bottom: 1px solid #313244; }
            QStatusBar { background-color: #181825; color: #a6adc8; font-size: 12px; border-top: 1px solid #313244; }
            QLabel { color: #cdd6f4; }
            QPushButton {
                background-color: #89b4fa; color: #1e1e2e; font-weight: bold;
                border: none; border-radius: 4px; padding: 6px 16px;
            }
            QPushButton:hover { background-color: #74c7ec; }
            QPushButton:pressed { background-color: #89dceb; }
            """
        )

    @Slot()
    def _toggle_connection(self) -> None:
        if not self._connected:
            self._start_stream()
        else:
            self._stop_stream()

    def _start_stream(self) -> None:
        ip_text = self._ip_input.text().strip()
        if not ip_text:
            self._status_label.setText("Stan: Podaj adres IP")
            return

        host = ip_text
        port = self.DEFAULT_PORT
        if ":" in ip_text:
            host, port_str = ip_text.rsplit(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                pass

        self._frame_provider = NetworkFrameProvider(host=host, port=port)

        self._connected = True
        self._btn_connect.setText("Rozłącz")
        self._btn_connect.setStyleSheet(
            "QPushButton { background-color: #f38ba8; color: #1e1e2e; font-weight: bold;"
            " border: none; border-radius: 4px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #eba0ac; }"
        )
        self._ip_input.setEnabled(False)
        self._status_label.setText(f"Stan: Łączenie… ({host}:{port})")

        self._worker_thread = QThread()
        self._worker = FrameWorker(self._frame_provider)
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.start_loop)
        self._worker.frame_ready.connect(self._video_widget.update_frame, Qt.ConnectionType.QueuedConnection)
        self._worker.fps_updated.connect(self._on_fps_updated, Qt.ConnectionType.QueuedConnection)

        self._worker_thread.start()

    def _stop_stream(self) -> None:
        if self._worker is not None:
            self._worker.stop_loop()
        if self._worker_thread is not None:
            self._worker_thread.quit()
            self._worker_thread.wait(3000)
            self._worker_thread = None
        self._worker = None
        self._frame_provider = None

        self._connected = False
        self._btn_connect.setText("Połącz")
        self._btn_connect.setStyleSheet("")
        self._ip_input.setEnabled(True)
        self._status_label.setText("Stan: Rozłączono")
        self._fps_label.setText("FPS: –")

    @Slot(float)
    def _on_fps_updated(self, fps: float) -> None:
        self._fps_label.setText(f"FPS: {fps:.1f}")

    def closeEvent(self, event) -> None:
        self._stop_stream()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()