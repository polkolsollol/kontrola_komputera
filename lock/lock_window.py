from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPainter, QColor, QScreen
from PySide6.QtWidgets import QApplication, QWidget


class LockWindow(QWidget):
    """Pełnoekranowe okno blokady — czarny ekran z komunikatem."""

    def __init__(self, screen: QScreen | None = None) -> None:
        super().__init__()
        self._target_screen = screen
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # nie pojawia się na pasku zadań
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

    def show_fullscreen(self) -> None:
        """Pokaż na pełnym ekranie docelowego monitora."""
        if self._target_screen is not None:
            geo = self._target_screen.geometry()
        else:
            screen = QApplication.primaryScreen()
            geo = screen.geometry() if screen else self.screen().geometry()

        self.setGeometry(geo)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.grabKeyboard()

    # ----- Rysowanie -----

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0))

        painter.setPen(QColor(255, 255, 255))
        font = QFont("Arial", 48, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignCenter,
            "KOMPUTER ZOSTAŁ ZABLOKOWANY",
        )
        painter.end()

    # ----- Blokada interakcji -----

    def mousePressEvent(self, event) -> None:
        event.ignore()

    def keyPressEvent(self, event) -> None:
        # Blokujemy wszystko łącznie z Alt+F4
        event.accept()

    def closeEvent(self, event) -> None:
        # Zapobiegamy zamknięciu przez Alt+F4 / menedżer okien
        event.ignore()

    def force_close(self) -> None:
        """Jedyny sposób zamknięcia — wywoływany przez LockManager.unlock()."""
        self.releaseKeyboard()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.close()