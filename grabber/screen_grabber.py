import threading
import time
import cv2
import numpy as np
import mss

# TODO dla osoby od grabbera:
# - [DONE] naprawic wciecia metod get_latest_frame, _capture_loop, __enter__ i testu __main__;
# - [DONE] importowac FrameProvider/FrameData z core.interfaces zamiast lokalnego duplikatu;
# - [DONE] zostawic w FrameData.pixels skompresowany JPEG gotowy do wyslania przez siec.

from core.interfaces import FrameProvider, FrameData


class ScreenGrabber(FrameProvider):
    """
    Klasa przechwytująca zawartość ekranu za pomocą biblioteki mss,
    a następnie kompresująca każdą klatkę do formatu JPEG przy użyciu OpenCV.

    Przechwytywanie odbywa się w osobnym wątku demona działającym w tle,
    dzięki czemu główny wątek aplikacji nie jest blokowany. Najnowsza
    klatka jest przechowywana w pamięci i może być pobrana w dowolnym
    momencie przez get_latest_frame().

    Klasa implementuje interfejs FrameProvider oraz protokół context managera
    (with), co pozwala na wygodne zarządzanie cyklem życia obiektu.

    Przykład użycia:
        with ScreenGrabber(monitor_index=1, jpeg_quality=80) as grabber:
            frame = grabber.get_latest_frame()
    """

    def __init__(self, monitor_index: int = 1, jpeg_quality: int = 75):
         """
        Inicjalizuje grabber ekranu i tworzy instancję mss do przechwytywania.

        Wątek przechwytywania NIE jest tu uruchamiany — należy wywołać
        start() lub użyć obiektu jako context managera (with).

        Args:
            monitor_index: Indeks monitora do przechwytywania zgodny z
                           numeracją mss (1 = główny monitor, 2 = drugi itd.).
                           Monitor 0 w mss oznacza wirtualny ekran zbiorczy.
            jpeg_quality:  Jakość kompresji JPEG w skali 0–100.
                           Wyższe wartości = lepsza jakość, większy rozmiar.
                           Domyślnie 75 — dobry kompromis dla transmisji sieciowej.
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

    def _capture_loop(self):
        """Pętla przechwytywania działająca w wątku."""
        try:
            while self._running:
                # Przechwytanie surowego ekranu
                screenshot = self._mss.grab(self._mss.monitors[self.monitor_index])

                # Konwersja do numpy array
                frame_bgra = np.array(screenshot)

                # Konwersja BGRA → BGR (OpenCV format)
                frame_bgr = cv2.cvtColor(frame_bgra, cv2.COLOR_BGRA2BGR)

                # Kompresja do JPEG
                ret, jpeg_bytes = cv2.imencode(
                    '.jpg',
                    frame_bgr,
                    [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
                )

                if ret:
                    # Zapamiętanie klatki z timestampem
                    # pixels zawiera skompresowany JPEG gotowy do wysłania przez sieć
                    frame_data = FrameData(
                        pixels=jpeg_bytes.tobytes(),
                        width=frame_bgra.shape[1],
                        height=frame_bgra.shape[0],
                        timestamp=time.time()
                    )

                    with self._lock:
                        self._latest_frame = frame_data
        except Exception as e:
            print(f"[ScreenGrabber] Błąd w pętli przechwytywania: {e}")

    def __enter__(self):
        """Context manager support."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support."""
        self.stop()


# Przykład użycia (do testów):
if __name__ == "__main__":
    grabber = ScreenGrabber(jpeg_quality=75)
    grabber.start()

    try:
        for i in range(5):
            frame = grabber.get_latest_frame()
            print(f"Klatka {i}: {frame.width}x{frame.height}, {len(frame.pixels)} bajtów")
            time.sleep(1)
    finally:
        grabber.stop()