from __future__ import annotations

import os
import sys
import threading
import time
from typing import Optional

from dotenv import load_dotenv
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


# ---------------------------------------------------------------------------
# Warstwa sieciowa – odbieranie klatek w wątku tła
# ---------------------------------------------------------------------------

class NetworkFrameProvider(FrameProvider):
    """Receive frames in the background and expose the newest one."""

    def __init__(self, host: str, port: int = 9000, reconnect_delay: float = 2.0) -> None:
        self.host = host
        self.port = port
        self.reconnect_delay = reconnect_delay
        self._receiver = NetworkReceiver(host=host, port=port, timeout=3.0)
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._latest_frame: Optional[FrameData] = None
        self._last_error: Optional[str] = None

    def start(self) -> None:
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
        self._running = False
        self._receiver.stop()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def get_latest_frame(self) -> FrameData:
        with self._lock:
            if self._latest_frame is None:
                if self._last_error:
                    raise RuntimeError(self._last_error)
                raise RuntimeError("Waiting for first frame")
            return self._latest_frame

    def _receive_loop(self) -> None:
        while self._running:
            try:
                self._last_error = f"Connecting to {self.host}:{self.port}..."
                self._receiver.connect()
                self._last_error = None

                while self._running:
                    frame = self._receiver.receive_frame()
                    with self._lock:
                        self._latest_frame = frame
                        self._last_error = None
            except Exception as exc:  # noqa: BLE001
                if not self._running:
                    break
                self._receiver.stop()
                self._last_error = str(exc)
                time.sleep(self.reconnect_delay)


# ---------------------------------------------------------------------------
# Worker Qt – konwersja klatek i licznik FPS
# ---------------------------------------------------------------------------

class FrameWorker(QObject):
    frame_ready = Signal(QImage)
    fps_updated = Signal(float)

    DEFAULT_INTERVAL_MS = 15

    def __init__(self, provider: FrameProvider, interval_ms: int = DEFAULT_INTERVAL_MS) -> None:
        super().__init__()
        self._provider = provider
        self._interval_ms = interval_ms
        self._running = False
        self._timer: Optional[QTimer] = None
        self._fps_frame_count = 0
        self._fps_last_time = time.time()
        self._last_timestamp: Optional[float] = None

    @Slot()
    def start_loop(self) -> None:
        self._provider.start()
        self._running = True
        self._timer = QTimer()
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self._interval_ms)

    @Slot()
    def stop_loop(self) -> None:
        self._running = False
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        self._provider.stop()

    def _tick(self) -> None:
        if not self._running:
            return

        try:
            frame_data = self._provider.get_latest_frame()
        except RuntimeError:
            return

        if self._last_timestamp == frame_data.timestamp:
            return

        self._last_timestamp = frame_data.timestamp
        image = self._frame_data_to_qimage(frame_data)
        if image.isNull():
            return

        self.frame_ready.emit(image)
        self._fps_frame_count += 1

        now = time.time()
        elapsed = now - self._fps_last_time
        if elapsed >= 1.0:
            self.fps_updated.emit(self._fps_frame_count / elapsed)
            self._fps_frame_count = 0
            self._fps_last_time = now

    @staticmethod
    def _frame_data_to_qimage(frame: FrameData) -> QImage:
        image = QImage()
        if image.loadFromData(frame.pixels):
            return image
        return QImage()


# ---------------------------------------------------------------------------
# Widget wyświetlający wideo
# ---------------------------------------------------------------------------

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

    def clear_frame(self) -> None:
        self._pixmap = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if self._pixmap is not None and not self._pixmap.isNull():
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
                "Brak strumienia wideo\nPodaj adres nadawcy i kliknij Polacz",
            )

        painter.end()


# ---------------------------------------------------------------------------
# Okno logowania administratora
# ---------------------------------------------------------------------------

class LoginWindow(QWidget):
    """
    Ekran logowania wyświetlany przy starcie aplikacji odbiornika.

    Dane logowania (login i hasło) są wczytywane z pliku .env za pomocą
    biblioteki python-dotenv. Klucze w pliku to ADMIN_USERNAME i ADMIN_PASSWORD.

    Po poprawnym zalogowaniu emitowany jest sygnał ``login_successful``,
    który uruchamia właściwe okno główne aplikacji. Przy błędnych danych
    wyświetlany jest komunikat, a pole hasła jest czyszczone.
    """

    login_successful = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Logowanie – Panel Administratora")
        self.setFixedSize(420, 340)
        self._load_credentials()
        self._build_ui()
        self._apply_styles()

    # ------------------------------------------------------------------
    # Inicjalizacja
    # ------------------------------------------------------------------

    def _load_credentials(self) -> None:
        """Wczytuje dane admina z pliku .env (szukany w katalogu roboczym)."""
        load_dotenv()
        self._admin_user = os.getenv("ADMIN_USERNAME", "admin")
        self._admin_pass = os.getenv("ADMIN_PASSWORD", "admin")

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(14)

        # Tytuł
        title = QLabel("Panel Administratora")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("loginTitle")

        # Pole loginu
        self._user_input = QLineEdit()
        self._user_input.setPlaceholderText("Login")
        self._user_input.setFixedHeight(40)

        # Pole hasła
        self._pass_input = QLineEdit()
        self._pass_input.setPlaceholderText("Hasło")
        self._pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._pass_input.setFixedHeight(40)
        self._pass_input.returnPressed.connect(self._attempt_login)

        # Komunikat błędu (domyślnie ukryty)
        self._error_label = QLabel("")
        self._error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_label.setObjectName("errorLabel")
        self._error_label.setFixedHeight(20)

        # Przycisk logowania
        self._btn_login = QPushButton("Zaloguj się")
        self._btn_login.setFixedHeight(42)
        self._btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_login.clicked.connect(self._attempt_login)

        layout.addWidget(title)
        layout.addSpacing(6)
        layout.addWidget(self._user_input)
        layout.addWidget(self._pass_input)
        layout.addWidget(self._error_label)
        layout.addWidget(self._btn_login)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background-color: #1e1e2e;
            }
            #loginTitle {
                font-size: 20px;
                font-weight: bold;
                color: #89b4fa;
                margin-bottom: 4px;
            }
            QLineEdit {
                background: #313244;
                color: #cdd6f4;
                border: 1px solid #585b70;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #89b4fa;
            }
            #errorLabel {
                color: #f38ba8;
                font-size: 12px;
            }
            QPushButton {
                background-color: #89b4fa;
                color: #1e1e2e;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover  { background-color: #74c7ec; }
            QPushButton:pressed { background-color: #89dceb; }
            """
        )

    # ------------------------------------------------------------------
    # Logika logowania
    # ------------------------------------------------------------------

    @Slot()
    def _attempt_login(self) -> None:
        """
        Sprawdza podane dane względem wartości z .env.
        Sukces  → emituje login_successful i zamyka okno logowania.
        Błąd    → pokazuje komunikat, czyści pole hasła.
        """
        username = self._user_input.text().strip()
        password = self._pass_input.text()

        if username == self._admin_user and password == self._admin_pass:
            self.login_successful.emit()
            self.close()
        else:
            self._error_label.setText("Nieprawidłowy login lub hasło. Spróbuj ponownie.")
            self._pass_input.clear()
            self._pass_input.setFocus()


# ---------------------------------------------------------------------------
# Główne okno aplikacji
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
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

    def _build_ui(self, initial_host: str, initial_port: int) -> None:
        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("toolbar")
        toolbar_layout = QHBoxLayout(toolbar_frame)
        toolbar_layout.setContentsMargins(12, 8, 12, 8)
        toolbar_layout.setSpacing(8)

        host_label = QLabel("Adres nadawcy:")
        host_label.setStyleSheet("color: #cdd6f4; font-weight: bold;")
        self._address_input = QLineEdit()
        self._address_input.setPlaceholderText("np. 192.168.1.100 albo 192.168.1.100:9000")
        self._address_input.setText(
            f"{initial_host}:{initial_port}" if initial_host else ""
        )
        self._address_input.setFixedWidth(320)
        self._address_input.returnPressed.connect(self._toggle_connection)
        self._address_input.setStyleSheet(
            "QLineEdit { background: #313244; color: #cdd6f4; border: 1px solid #585b70;"
            " border-radius: 4px; padding: 4px 8px; }"
            "QLineEdit:focus { border-color: #89b4fa; }"
        )

        self._btn_connect = QPushButton("Polacz")
        self._btn_connect.setFixedWidth(130)
        self._btn_connect.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_connect.clicked.connect(self._toggle_connection)

        toolbar_layout.addWidget(host_label)
        toolbar_layout.addWidget(self._address_input)
        toolbar_layout.addWidget(self._btn_connect)
        toolbar_layout.addStretch()

        self._video_widget = VideoWidget()

        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(toolbar_frame)
        main_layout.addWidget(self._video_widget, stretch=1)
        self.setCentralWidget(central)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_label = QLabel("Stan: Rozlaczono")
        self._fps_label = QLabel("FPS: -")
        self._status_bar.addWidget(self._status_label, stretch=1)
        self._status_bar.addPermanentWidget(self._fps_label)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background-color: #1e1e2e; }
            #toolbar { background-color: #181825; border-bottom: 1px solid #313244; }
            QStatusBar {
                background-color: #181825;
                color: #a6adc8;
                font-size: 12px;
                border-top: 1px solid #313244;
            }
            QLabel { color: #cdd6f4; }
            QPushButton {
                background-color: #89b4fa;
                color: #1e1e2e;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover { background-color: #74c7ec; }
            QPushButton:pressed { background-color: #89dceb; }
            """
        )

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._auto_connect:
            self._auto_connect = False
            self._start_stream()

    @Slot()
    def _toggle_connection(self) -> None:
        if self._connected:
            self._stop_stream()
        else:
            self._start_stream()

    def _start_stream(self) -> None:
        address = self._address_input.text().strip()
        if not address:
            self._status_label.setText("Stan: Podaj adres IP nadawcy")
            return

        host, port = self._parse_address(address)
        if host is None:
            self._status_label.setText("Stan: Niepoprawny adres lub port")
            return

        self._frame_provider = NetworkFrameProvider(host=host, port=port)
        self._worker_thread = QThread()
        self._worker = FrameWorker(self._frame_provider)
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.start_loop)
        self._worker.frame_ready.connect(self._video_widget.update_frame, Qt.ConnectionType.QueuedConnection)
        self._worker.frame_ready.connect(self._on_first_frame, Qt.ConnectionType.QueuedConnection)
        self._worker.fps_updated.connect(self._on_fps_updated, Qt.ConnectionType.QueuedConnection)
        self._worker_thread.start()

        self._connected = True
        self._address_input.setEnabled(False)
        self._btn_connect.setText("Rozlacz")
        self._btn_connect.setStyleSheet(
            "QPushButton { background-color: #f38ba8; color: #1e1e2e; font-weight: bold;"
            " border: none; border-radius: 4px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #eba0ac; }"
        )
        self._status_label.setText(f"Stan: Laczenie z {host}:{port}...")

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
        self._address_input.setEnabled(True)
        self._btn_connect.setText("Polacz")
        self._btn_connect.setStyleSheet("")
        self._status_label.setText("Stan: Rozlaczono")
        self._fps_label.setText("FPS: -")
        self._video_widget.clear_frame()

    def _parse_address(self, address: str) -> tuple[Optional[str], int]:
        host = address
        port = self._default_port

        if ":" in address:
            host, raw_port = address.rsplit(":", 1)
            if not host:
                return None, port
            try:
                port = int(raw_port)
            except ValueError:
                return None, port

        return host, port

    @Slot(QImage)
    def _on_first_frame(self, _image: QImage) -> None:
        self._status_label.setText(f"Stan: Polaczono ({self._address_input.text().strip()})")
        if self._worker is not None:
            try:
                self._worker.frame_ready.disconnect(self._on_first_frame)
            except RuntimeError:
                pass

    @Slot(float)
    def _on_fps_updated(self, fps: float) -> None:
        self._fps_label.setText(f"FPS: {fps:.1f}")

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._connected:
            self._stop_stream()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Punkt wejścia
# ---------------------------------------------------------------------------

def run_receiver_ui(
    initial_host: str = "",
    initial_port: int = 9000,
    auto_connect: bool = False,
) -> int:
    app = QApplication(sys.argv)

    # Tworzymy okno główne z góry, ale jeszcze go nie pokazujemy
    main_window = MainWindow(
        initial_host=initial_host,
        initial_port=initial_port,
        auto_connect=auto_connect,
    )

    # Pokazujemy ekran logowania – MainWindow otworzy się dopiero po sukcesie
    login_window = LoginWindow()
    login_window.login_successful.connect(main_window.show)
    login_window.show()

    return app.exec()


def main() -> None:
    raise SystemExit(run_receiver_ui())


if __name__ == "__main__":
    main()