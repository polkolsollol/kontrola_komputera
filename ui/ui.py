from __future__ import annotations

import sys
import threading
import time
from typing import Optional

from PySide6.QtCore import QObject, QPoint, QRect, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from core.interfaces import FrameData, FrameProvider
from network.connection import NetworkReceiver


class NetworkFrameProvider(FrameProvider):
    """
    Implementacja FrameProvider, która odbiera klatki w tle z sieci.

    - Używa osobnego wątku (threading.Thread) do odbioru danych
    - Przechowuje tylko najnowszą klatkę (nadpisywanie)
    - Obsługuje automatyczne ponowne łączenie
    """

    def __init__(self, host: str, port: int = 9000, reconnect_delay: float = 2.0) -> None:
        """
        :param host: adres IP lub hostname nadawcy
        :param port: port TCP
        :param reconnect_delay: czas (sekundy) przed ponowną próbą po błędzie
        """
        self.host = host
        self.port = port
        self.reconnect_delay = reconnect_delay

        # Klasa odpowiedzialna za niskopoziomową komunikację sieciową
        self._receiver = NetworkReceiver(host=host, port=port, timeout=3.0)

        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Lock do synchronizacji dostępu do klatki między wątkami
        self._lock = threading.Lock()

        self._latest_frame: Optional[FrameData] = None
        self._last_error: Optional[str] = None

    def start(self) -> None:
        """Uruchamia wątek odbierający dane."""
        if self._running:
            return

        self._running = True

        self._thread = threading.Thread(
            target=self._receive_loop,
            daemon=True,
            name="NetworkFrameProvider",
        )
        self._thread.start()

    def stop(self) -> None:
        """Zatrzymuje odbieranie danych i zamyka wątek."""
        self._running = False
        self._receiver.stop()

        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def get_latest_frame(self) -> FrameData:
        """
        Zwraca najnowszą dostępną klatkę.

        :raises RuntimeError: gdy brak danych lub wystąpił błąd
        """
        with self._lock:
            if self._latest_frame is None:
                if self._last_error:
                    raise RuntimeError(self._last_error)
                raise RuntimeError("Waiting for first frame")
            return self._latest_frame

    def _receive_loop(self) -> None:
        """
        Główna pętla wątku odbierającego.

        - próbuje się połączyć
        - odbiera klatki
        - zapisuje najnowszą
        - w razie błędu ponawia połączenie
        """
        while self._running:
            try:
                self._last_error = f"Connecting to {self.host}:{self.port}..."
                self._receiver.connect()
                self._last_error = None

                while self._running:
                    frame = self._receiver.receive_frame()

                    # zapis najnowszej klatki (thread-safe)
                    with self._lock:
                        self._latest_frame = frame
                        self._last_error = None

            except Exception as exc:
                if not self._running:
                    break

                self._receiver.stop()
                self._last_error = str(exc)

                # odczekaj przed reconnectem
                time.sleep(self.reconnect_delay)


class FrameWorker(QObject):
    """
    Worker Qt odpowiedzialny za:
    - pobieranie klatek z FrameProvider
    - konwersję do QImage
    - emitowanie sygnałów do GUI
    - obliczanie FPS
    """

    frame_ready = Signal(QImage)   # nowa klatka do wyświetlenia
    fps_updated = Signal(float)    # aktualizacja FPS

    DEFAULT_INTERVAL_MS = 15  # ~66 FPS

    def __init__(self, provider: FrameProvider, interval_ms: int = DEFAULT_INTERVAL_MS) -> None:
        super().__init__()
        self._provider = provider
        self._interval_ms = interval_ms

        self._running = False
        self._timer: Optional[QTimer] = None

        # zmienne do FPS
        self._fps_frame_count = 0
        self._fps_last_time = time.time()

        # ostatni timestamp klatki (aby nie renderować duplikatów)
        self._last_timestamp: Optional[float] = None

    @Slot()
    def start_loop(self) -> None:
        """Uruchamia pętlę aktualizacji w wątku Qt."""
        self._provider.start()
        self._running = True

        self._timer = QTimer()
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self._interval_ms)

    @Slot()
    def stop_loop(self) -> None:
        """Zatrzymuje worker."""
        self._running = False

        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None

        self._provider.stop()

    def _tick(self) -> None:
        """
        Wywoływane cyklicznie przez QTimer.

        - pobiera klatkę
        - sprawdza czy nowa
        - konwertuje do QImage
        - emituje sygnał
        """
        if not self._running:
            return

        try:
            frame_data = self._provider.get_latest_frame()
        except RuntimeError:
            return

        # pomijamy tę samą klatkę
        if self._last_timestamp == frame_data.timestamp:
            return

        self._last_timestamp = frame_data.timestamp

        image = self._frame_data_to_qimage(frame_data)
        if image.isNull():
            return

        self.frame_ready.emit(image)
        self._fps_frame_count += 1

        # liczenie FPS co 1 sekundę
        now = time.time()
        elapsed = now - self._fps_last_time
        if elapsed >= 1.0:
            self.fps_updated.emit(self._fps_frame_count / elapsed)
            self._fps_frame_count = 0
            self._fps_last_time = now

    @staticmethod
    def _frame_data_to_qimage(frame: FrameData) -> QImage:
        """
        Konwertuje FrameData (bytes) na QImage.
        """
        image = QImage()
        if image.loadFromData(frame.pixels):
            return image
        return QImage()


class VideoWidget(QWidget):
    """
    Widget odpowiedzialny za wyświetlanie obrazu wideo.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None

        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # tło gdy brak obrazu
        self.setStyleSheet("background-color: #1e1e2e;")

    @Slot(QImage)
    def update_frame(self, image: QImage) -> None:
        """Aktualizuje aktualną klatkę."""
        self._pixmap = QPixmap.fromImage(image)
        self.update()

    def clear_frame(self) -> None:
        """Czyści obraz."""
        self._pixmap = None
        self.update()

    def paintEvent(self, event) -> None:
        """
        Renderowanie widgetu.

        - jeśli jest obraz → skaluj i wyśrodkuj
        - jeśli nie → pokaż komunikat
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if self._pixmap is not None and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            # centrowanie obrazu
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2

            painter.drawPixmap(x, y, scaled)
        else:
            painter.setPen(QColor(120, 120, 140))
            painter.setFont(QFont("Sans", 16))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Brak strumienia wideo\nPodaj adres nadawcy i kliknij Polacz",
            )

        painter.end()


class MainWindow(QMainWindow):
    """
    Główne okno aplikacji.

    Odpowiada za:
    - UI
    - zarządzanie połączeniem
    - start/stop workerów
    """

    def __init__(
        self,
        initial_host: str = "",
        initial_port: int = 9000,
        auto_connect: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle("Odbiornik podgladu ekranu")
        self.resize(1100, 720)

        self._default_port = initial_port
        self._auto_connect = auto_connect
        self._connected = False

        self._frame_provider: Optional[FrameProvider] = None
        self._worker: Optional[FrameWorker] = None
        self._worker_thread: Optional[QThread] = None

        self._build_ui(initial_host, initial_port)
        self._apply_styles()

    # ---------------- UI ----------------

    def _build_ui(self, initial_host: str, initial_port: int) -> None:
        """Buduje interfejs użytkownika."""
        # toolbar
        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("toolbar")

        toolbar_layout = QHBoxLayout(toolbar_frame)

        host_label = QLabel("Adres nadawcy:")

        self._address_input = QLineEdit()
        self._address_input.setPlaceholderText("np. 192.168.1.100:9000")

        self._btn_connect = QPushButton("Polacz")
        self._btn_connect.clicked.connect(self._toggle_connection)

        toolbar_layout.addWidget(host_label)
        toolbar_layout.addWidget(self._address_input)
        toolbar_layout.addWidget(self._btn_connect)
        toolbar_layout.addStretch()

        # video
        self._video_widget = VideoWidget()

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(toolbar_frame)
        layout.addWidget(self._video_widget)

        self.setCentralWidget(central)

        # status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._status_label = QLabel("Stan: Rozlaczono")
        self._fps_label = QLabel("FPS: -")

        self._status_bar.addWidget(self._status_label, stretch=1)
        self._status_bar.addPermanentWidget(self._fps_label)

    def _apply_styles(self) -> None:
        """Ustawia style CSS dla aplikacji."""
        self.setStyleSheet("QMainWindow { background-color: #1e1e2e; }")

    # ---------------- LOGIKA ----------------

    @Slot()
    def _toggle_connection(self) -> None:
        """Przełącza stan połączenia."""
        if self._connected:
            self._stop_stream()
        else:
            self._start_stream()

    def _start_stream(self) -> None:
        """Rozpoczyna odbiór strumienia."""
        address = self._address_input.text().strip()
        if not address:
            self._status_label.setText("Stan: Podaj adres")
            return

        host, port = self._parse_address(address)
        if host is None:
            self._status_label.setText("Stan: Bledny adres")
            return

        # inicjalizacja provider + worker
        self._frame_provider = NetworkFrameProvider(host=host, port=port)

        self._worker_thread = QThread()
        self._worker = FrameWorker(self._frame_provider)
        self._worker.moveToThread(self._worker_thread)

        # sygnały
        self._worker_thread.started.connect(self._worker.start_loop)
        self._worker.frame_ready.connect(self._video_widget.update_frame)
        self._worker.fps_updated.connect(self._on_fps_updated)

        self._worker_thread.start()

        self._connected = True

    def _stop_stream(self) -> None:
        """Zatrzymuje odbiór."""
        if self._worker:
            self._worker.stop_loop()

        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait()

        self._connected = False
        self._video_widget.clear_frame()

    def _parse_address(self, address: str) -> tuple[Optional[str], int]:
        """Parsuje adres w formacie host:port."""
        host = address
        port = self._default_port

        if ":" in address:
            host, raw_port = address.rsplit(":", 1)
            try:
                port = int(raw_port)
            except ValueError:
                return None, port

        return host, port

    @Slot(float)
    def _on_fps_updated(self, fps: float) -> None:
        """Aktualizuje etykietę FPS."""
        self._fps_label.setText(f"FPS: {fps:.1f}")


def run_receiver_ui(
    initial_host: str = "",
    initial_port: int = 9000,
    auto_connect: bool = False,
) -> int:
    """
    Uruchamia aplikację Qt.
    """
    app = QApplication(sys.argv)

    window = MainWindow(
        initial_host=initial_host,
        initial_port=initial_port,
        auto_connect=auto_connect,
    )

    window.show()
    return app.exec()


def main() -> None:
    """Punkt wejścia programu."""
    raise SystemExit(run_receiver_ui())


if __name__ == "__main__":
    main()