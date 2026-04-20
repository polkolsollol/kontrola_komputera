"""
ui.py – Warstwa interfejsu użytkownika (PySide6) dla aplikacji zdalnego podglądu ekranu.

Architektura
────────────
MainWindow          – Główne okno aplikacji (QMainWindow). Zawiera toolbar
                      z polem IP, przyciskiem Połącz/Rozłącz oraz paskiem
                      statusu. Centralny widget to VideoWidget.

VideoWidget         – Dedykowany widget (QWidget) do wyświetlania strumienia
                      klatek. Renderuje QPixmap za pomocą QPainter,
                      skalując obraz do rozmiaru widgetu z zachowaniem
                      proporcji (aspect‑ratio).

SimulatedFrameProvider
                    – Konkretna implementacja interfejsu FrameProvider
                      z interfaces.py. Generuje kolorowe klatki testowe
                      (gradient + ruchomy znacznik czasu), co pozwala
                      uruchomić i przetestować UI bez modułów sieciowych
                      lub przechwytywania ekranu.

FrameWorker         – QObject przenoszony do QThread. Cyklicznie pobiera
                      klatkę z aktualnego FrameProvider i emituje sygnał
                      frame_ready(QImage). Dzięki temu pętla odświeżania
                      nie blokuje wątku GUI.

Punkty integracji (TODO)
────────────────────────
1. Moduł sieciowy   → MainWindow.set_frame_provider(provider)
                       lub MainWindow.on_frame_received(frame_bytes)
2. Screen capture    → Podać własną implementację FrameProvider do
                       MainWindow.set_frame_provider(provider)

Użycie standalone:
    python ui.py
"""

from __future__ import annotations

import io
import math
import struct
import sys
import time
from typing import Optional

from PySide6.QtCore import (
    QObject,
    QThread,
    QTimer,
    Signal,
    Slot,
    Qt,
    QSize,
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

# ──────────────────────────────────────────────
# Import kontraktu z interfaces.py
# ──────────────────────────────────────────────
from interfaces import FrameData, FrameProvider


# ═══════════════════════════════════════════════
# 1. SimulatedFrameProvider  (testowe źródło klatek)
# ═══════════════════════════════════════════════

class SimulatedFrameProvider(FrameProvider):
    """
    Generuje kolorowe klatki testowe (640×480, format RGBA).

    Klatki zawierają:
    * animowany gradient tła (barwa zmienia się w czasie),
    * ruchomy biały okrąg – łatwo ocenić płynność odświeżania,
    * aktualny timestamp – widać, że strumień jest „żywy".

    Klasa implementuje kontrakt FrameProvider, więc można ją
    podmienić 1:1 na prawdziwy moduł przechwytywania ekranu.
    """

    WIDTH = 640
    HEIGHT = 480

    def __init__(self) -> None:
        self._running: bool = False
        self._start_time: float = time.time()
        self._frame_counter: int = 0

    # -- FrameProvider interface ------------------------------------------------

    def start(self) -> None:
        """Uruchamia symulowane przechwytywanie."""
        self._running = True
        self._start_time = time.time()
        self._frame_counter = 0

    def stop(self) -> None:
        """Zatrzymuje symulowane przechwytywanie."""
        self._running = False

    def get_latest_frame(self) -> FrameData:
        """
        Zwraca nową klatkę testową w formacie RGBA (surowe bajty).

        Returns
        -------
        FrameData
            Obiekt z polami: pixels, width, height, timestamp.
        """
        self._frame_counter += 1
        t = time.time() - self._start_time

        img = QImage(self.WIDTH, self.HEIGHT, QImage.Format.Format_RGBA8888)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # -- tło: animowany gradient -------------------------------------------
        hue_offset = int(t * 30) % 360
        gradient = QLinearGradient(0, 0, self.WIDTH, self.HEIGHT)
        gradient.setColorAt(0.0, QColor.fromHsv(hue_offset % 360, 180, 220))
        gradient.setColorAt(0.5, QColor.fromHsv((hue_offset + 120) % 360, 180, 200))
        gradient.setColorAt(1.0, QColor.fromHsv((hue_offset + 240) % 360, 180, 220))
        painter.fillRect(img.rect(), QBrush(gradient))

        # -- ruchomy okrąg -----------------------------------------------------
        cx = int(self.WIDTH / 2 + 150 * math.cos(t * 2))
        cy = int(self.HEIGHT / 2 + 100 * math.sin(t * 3))
        painter.setPen(QPen(QColor(255, 255, 255, 200), 3))
        painter.setBrush(QBrush(QColor(255, 255, 255, 80)))
        painter.drawEllipse(QPoint(cx, cy), 40, 40)

        # -- tekst z timestampem i FPS -----------------------------------------
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Monospace", 14, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(
            QRect(10, 10, self.WIDTH - 20, 40),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            f"Symulacja  |  t = {t:.1f}s  |  klatka #{self._frame_counter}",
        )

        font_small = QFont("Monospace", 11)
        painter.setFont(font_small)
        painter.drawText(
            QRect(10, self.HEIGHT - 35, self.WIDTH - 20, 30),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
            "źródło: SimulatedFrameProvider  (podmień na NetworkProvider / CaptureProvider)",
        )

        painter.end()

        # QImage → surowe bajty RGBA
        raw_bytes: bytes = img.bits().tobytes()  # type: ignore[union-attr]
        return FrameData(
            pixels=raw_bytes,
            width=self.WIDTH,
            height=self.HEIGHT,
            timestamp=time.time(),
        )


# ═══════════════════════════════════════════════
# 2. FrameWorker  (wątek pobierający klatki)
# ═══════════════════════════════════════════════

class FrameWorker(QObject):
    """
    Worker działający w osobnym QThread.

    Cyklicznie odpytuje FrameProvider.get_latest_frame()
    i emituje sygnał `frame_ready` z gotowym QImage.
    Dzięki temu wątek GUI nie jest blokowany.

    Sygnały
    -------
    frame_ready(QImage)
        Emitowany po każdej nowej klatce.
    fps_updated(float)
        Aktualny FPS (emitowany co sekundę).
    """

    frame_ready = Signal(QImage)
    fps_updated = Signal(float)

    # Domyślna docelowa częstotliwość odświeżania [ms]
    DEFAULT_INTERVAL_MS = 33  # ~30 FPS

    def __init__(self, provider: FrameProvider, interval_ms: int = DEFAULT_INTERVAL_MS) -> None:
        super().__init__()
        self._provider: FrameProvider = provider
        self._interval_ms: int = interval_ms
        self._running: bool = False
        self._timer: Optional[QTimer] = None

        # FPS measurement
        self._fps_frame_count: int = 0
        self._fps_last_time: float = time.time()

    # -- publiczne API (wywoływane z głównego wątku) ---------------------------

    def set_provider(self, provider: FrameProvider) -> None:
        """
        Pozwala w locie podmienić źródło klatek (np. z symulacji na sieć).

        Punkt integracji – moduł sieciowy lub screen capture może
        dostarczyć własny FrameProvider i wywołać tę metodę.
        """
        self._provider = provider

    @Slot()
    def start_loop(self) -> None:
        """Slot wywoływany po przeniesieniu workera do QThread.start()."""
        self._running = True
        self._provider.start()
        self._timer = QTimer()
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self._interval_ms)

    @Slot()
    def stop_loop(self) -> None:
        """Zatrzymuje pętlę odświeżania."""
        self._running = False
        if self._timer is not None:
            self._timer.stop()
        self._provider.stop()

    # -- wewnętrzne ------------------------------------------------------------

    def _tick(self) -> None:
        if not self._running:
            return
        frame_data = self._provider.get_latest_frame()
        qimg = self._frame_data_to_qimage(frame_data)
        self.frame_ready.emit(qimg)

        # FPS tracking
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
        """
        Konwertuje FrameData (surowe bajty RGBA) na QImage.

        Dla integracji z modułem sieciowym, który przesyła JPEG:
            frame_bytes → QImage (patrz MainWindow.on_frame_received).
        """
        img = QImage(
            fd.pixels,
            fd.width,
            fd.height,
            fd.width * 4,  # bytes per line (RGBA = 4)
            QImage.Format.Format_RGBA8888,
        )
        # .copy() gwarantuje, że dane nie zostaną zwolnione
        return img.copy()


# ═══════════════════════════════════════════════
# 3. VideoWidget  (wyświetlanie strumienia)
# ═══════════════════════════════════════════════

class VideoWidget(QWidget):
    """
    Widget renderujący bieżącą klatkę (QPixmap) za pomocą QPainter.

    Obraz jest skalowany z zachowaniem proporcji (aspect‑ratio fit)
    i centrowany w dostępnej przestrzeni.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Ciemne tło, żeby obraz był dobrze widoczny
        self.setStyleSheet("background-color: #1e1e2e;")

    # -- publiczny slot --------------------------------------------------------

    @Slot(QImage)
    def update_frame(self, image: QImage) -> None:
        """Przyjmuje QImage i zleca przerysowanie widgetu."""
        self._pixmap = QPixmap.fromImage(image)
        self.update()  # schedules paintEvent

    # -- Qt overrides ----------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if self._pixmap and not self._pixmap.isNull():
            # Skalowanie z zachowaniem proporcji
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            # Placeholder – brak klatek
            painter.setPen(QColor(120, 120, 140))
            painter.setFont(QFont("Sans", 16))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Brak strumienia wideo\nKliknij \u00abPo\u0142\u0105cz\u00bb, aby rozpocz\u0105\u0107",
            )
        painter.end()


# ═══════════════════════════════════════════════
# 4. MainWindow  (główne okno aplikacji)
# ═══════════════════════════════════════════════

class MainWindow(QMainWindow):
    """
    Główne okno aplikacji zdalnego podglądu ekranu.

    Odpowiedzialności:
    * layout UI (pole IP, przycisk, widget wideo, status bar),
    * zarządzanie cyklem życia FrameWorker + QThread,
    * zmiana stanu wizualnego (Połącz ↔ Rozłącz),
    * punkty integracji dla modułów sieciowych i screen‑capture.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Zdalny Podgląd Ekranu")
        self.resize(960, 640)

        self._connected: bool = False

        # -- frame provider (domyślnie symulacja) ------------------------------
        self._frame_provider: FrameProvider = SimulatedFrameProvider()

        # -- worker / thread (tworzone przy „Połącz") --------------------------
        self._worker: Optional[FrameWorker] = None
        self._worker_thread: Optional[QThread] = None

        # -- budowa UI ---------------------------------------------------------
        self._build_ui()
        self._apply_styles()

    # ── budowa interfejsu ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # --- toolbar ----------------------------------------------------------
        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("toolbar")
        toolbar_layout = QHBoxLayout(toolbar_frame)
        toolbar_layout.setContentsMargins(12, 8, 12, 8)

        lbl_ip = QLabel("Adres IP:")
        lbl_ip.setStyleSheet("color: #cdd6f4; font-weight: bold;")
        self._ip_input = QLineEdit()
        self._ip_input.setPlaceholderText("np. 192.168.1.100")
        self._ip_input.setFixedWidth(200)
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

        # --- video widget -----------------------------------------------------
        self._video_widget = VideoWidget()

        # --- centralny layout -------------------------------------------------
        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(toolbar_frame)
        main_layout.addWidget(self._video_widget, stretch=1)
        self.setCentralWidget(central)

        # --- status bar -------------------------------------------------------
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
            QStatusBar { background-color: #181825; color: #a6adc8; font-size: 12px;
                         border-top: 1px solid #313244; }
            QLabel { color: #cdd6f4; }
            QPushButton {
                background-color: #89b4fa; color: #1e1e2e; font-weight: bold;
                border: none; border-radius: 4px; padding: 6px 16px;
            }
            QPushButton:hover { background-color: #74c7ec; }
            QPushButton:pressed { background-color: #89dceb; }
            """
        )

    # ── przycisk Połącz / Rozłącz ────────────────────────────────────────────

    @Slot()
    def _toggle_connection(self) -> None:
        if not self._connected:
            self._start_stream()
        else:
            self._stop_stream()

    def _start_stream(self) -> None:
        """Uruchamia strumień klatek (symulacja lub prawdziwy provider)."""
        ip = self._ip_input.text().strip()
        # Zmiana stanu wizualnego
        self._connected = True
        self._btn_connect.setText("Rozłącz")
        self._btn_connect.setStyleSheet(
            "QPushButton { background-color: #f38ba8; color: #1e1e2e; font-weight: bold;"
            " border: none; border-radius: 4px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #eba0ac; }"
        )
        self._ip_input.setEnabled(False)
        self._status_label.setText(f"Stan: Połączono ({ip or 'symulacja lokalna'})")

        # --- uruchomienie workera w osobnym wątku -----------------------------
        self._worker_thread = QThread()
        self._worker = FrameWorker(self._frame_provider, interval_ms=33)
        self._worker.moveToThread(self._worker_thread)

        # Sygnały
        self._worker_thread.started.connect(self._worker.start_loop)
        self._worker.frame_ready.connect(self._video_widget.update_frame, Qt.ConnectionType.QueuedConnection)
        self._worker.fps_updated.connect(self._on_fps_updated, Qt.ConnectionType.QueuedConnection)

        self._worker_thread.start()

    def _stop_stream(self) -> None:
        """Zatrzymuje strumień i przywraca UI do stanu 'rozłączony'."""
        if self._worker is not None:
            self._worker.stop_loop()
        if self._worker_thread is not None:
            self._worker_thread.quit()
            self._worker_thread.wait(2000)
            self._worker_thread = None
        self._worker = None

        self._connected = False
        self._btn_connect.setText("Połącz")
        self._btn_connect.setStyleSheet("")  # powrót do domyślnego stylu
        self._ip_input.setEnabled(True)
        self._status_label.setText("Stan: Rozłączono")
        self._fps_label.setText("FPS: –")

    @Slot(float)
    def _on_fps_updated(self, fps: float) -> None:
        self._fps_label.setText(f"FPS: {fps:.1f}")

    # ══════════════════════════════════════════════════════════════════════════
    # PUNKTY INTEGRACJI – API dla innych modułów zespołu
    # ══════════════════════════════════════════════════════════════════════════

    def set_frame_provider(self, provider: FrameProvider) -> None:
        """
        **Punkt integracji #1 — zmiana źródła klatek.**

        Pozwala podłączyć dowolną implementację FrameProvider
        (np. NetworkFrameProvider, ScreenCaptureProvider).

        Jeśli strumień jest aktywny, zostanie zrestartowany
        z nowym providerem.

        Przykład użycia (moduł screen capture):
        ─────────────────────────────────────────
            capture_provider = ScreenCaptureProvider(...)
            main_window.set_frame_provider(capture_provider)
        """
        was_connected = self._connected
        if was_connected:
            self._stop_stream()
        self._frame_provider = provider
        if was_connected:
            self._start_stream()

    def on_frame_received(self, frame_bytes: bytes) -> None:
        """
        **Punkt integracji #2 — odbiór pojedynczej klatki JPEG z sieci.**

        Metoda do podłączenia przez moduł sieciowy (NetworkClient).
        Konwertuje bajty JPEG → QImage i wyświetla na VideoWidget.

        Może być wywoływana bezpośrednio z wątku sieciowego —
        aktualizacja UI odbywa się bezpiecznie przez QMetaObject.

        Przykład użycia (moduł sieciowy):
        ──────────────────────────────────
            class NetworkClient:
                def __init__(self, main_window: MainWindow):
                    self._ui = main_window

                def _on_data_received(self, jpeg_data: bytes):
                    self._ui.on_frame_received(jpeg_data)

        Parameters
        ----------
        frame_bytes : bytes
            Dane obrazu zakodowane jako JPEG (lub PNG).
        """
        qimg = QImage()
        if qimg.loadFromData(frame_bytes):
            self._video_widget.update_frame(qimg)

    def get_target_ip(self) -> str:
        """
        **Punkt integracji #3 — odczyt adresu IP z pola tekstowego.**

        Moduł sieciowy może użyć tej metody, aby uzyskać
        adres serwera docelowego wpisany przez użytkownika.
        """
        return self._ip_input.text().strip()

    def is_connected(self) -> bool:
        """Zwraca aktualny stan wizualny połączenia."""
        return self._connected

    # TODO: Podłączenie modułu sieciowego (NetworkClient)
    #       ─────────────────────────────────────────────
    #       Moduł sieciowy powinien:
    #       1. Odczytać IP:  ip = main_window.get_target_ip()
    #       2. Po otrzymaniu klatki JPEG wywołać:
    #          main_window.on_frame_received(jpeg_bytes)
    #       Lub dostarczyć własny FrameProvider:
    #          main_window.set_frame_provider(network_provider)

    # TODO: Podłączenie modułu przechwytywania ekranu (ScreenCapture)
    #       ─────────────────────────────────────────────────────────
    #       Moduł screen capture powinien zaimplementować FrameProvider
    #       z interfaces.py, a następnie:
    #          main_window.set_frame_provider(capture_provider)

    # ── cleanup ──────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # noqa: N802
        """Upewnia się, że wątek workera jest zatrzymany przed zamknięciem."""
        self._stop_stream()
        super().closeEvent(event)


# ═══════════════════════════════════════════════
# 5. Punkt wejścia
# ═══════════════════════════════════════════════

def main() -> None:
    """Uruchomienie aplikacji z domyślnym SimulatedFrameProvider."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
