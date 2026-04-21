from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPainter, QColor
from PySide6.QtWidgets import QApplication, QWidget

class LockWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
    
    def show_fullscreen(self):
        """Pokaż fullscreen."""
        desktop = QApplication.desktop().screenGeometry()
        self.setGeometry(desktop)
        self.show()
        self.raise_()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0))
        
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Arial", 48, QFont.Weight.Bold)
        painter.setFont(font)
        
        painter.drawText(
            self.rect(), 
            Qt.AlignCenter, 
            "KOMPUTER ZOSTAŁ ZABLOKOWANY"
        )
    
    def mousePressEvent(self, event):
        event.ignore()
    
    def keyPressEvent(self, event):
        event.ignore()