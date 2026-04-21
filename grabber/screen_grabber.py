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
         """
        Uruchamia wątek przechwytywania w tle.

        Jeśli grabber już działa (self._running == True), metoda kończy się
        bez efektu — nie można uruchomić dwóch wątków jednocześnie.
        Wątek jest ustawiony jako daemon, więc zakończy się automatycznie
        gdy główny wątek programu się zamknie.
        """
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        print(f"[ScreenGrabber] Gestartet - monitor {self.monitor_index}")

    def stop(self):
        """
        Zatrzymuje przechwytywanie i zwalnia wszystkie zasoby.

        Ustawia flagę _running na False, co powoduje wyjście z pętli
        w _capture_loop(). Następnie czeka maksymalnie 2 sekundy na
        zakończenie wątku (join z timeout), po czym zamyka instancję mss.

        Metoda jest bezpieczna do wywołania nawet jeśli grabber nie był
        wcześniej uruchomiony.
        """
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        self._mss.close()
        print("[ScreenGrabber] Zatrzymany")

    def get_latest_frame(self) -> FrameData:
         """
        Zatrzymuje przechwytywanie i zwalnia wszystkie zasoby.

        Ustawia flagę _running na False, co powoduje wyjście z pętli
        w _capture_loop(). Następnie czeka maksymalnie 2 sekundy na
        zakończenie wątku (join z timeout), po czym zamyka instancję mss.

        Metoda jest bezpieczna do wywołania nawet jeśli grabber nie był
        wcześniej uruchomiony.
        """
        with self._lock:
            if self._latest_frame is None:
                raise RuntimeError("Brak dostępnych klatek - upewnij się, że start() został wywołany")
            return self._latest_frame

    def _capture_loop(self):
        """
        Główna pętla przechwytywania działająca w wątku tła.

        Wykonuje w kółko następujące kroki:
            1. Przechwycenie surowego zrzutu ekranu przez mss (format BGRA).
            2. Konwersja numpy array z BGRA na BGR (format natywny OpenCV).
            3. Kompresja klatki do JPEG z zadaną jakością.
            4. Zapisanie wyniku jako FrameData pod _latest_frame (z lockiem).

        Pętla kończy się gdy _running zostanie ustawione na False (przez stop()).
        Wszelkie wyjątki są łapane i logowane — pętla NIE rzuca wyjątków
        do wątku wywołującego, aby nie crashować całej aplikacji.
        """
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
        """
        Obsługa wejścia do bloku with — automatycznie uruchamia grabber.

        Dzięki temu można pisać:
            with ScreenGrabber() as grabber:
                ...
        zamiast ręcznie wywoływać start() i stop().
        """
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Obsługa wyjścia z bloku with — automatycznie zatrzymuje grabber.

        Wywoływane zarówno przy normalnym wyjściu, jak i przy wyjątku.
        Zwraca None (falsy), więc wyjątki są propagowane dalej — nie są tłumione.

        Args:
            exc_type: Typ wyjątku (None jeśli brak)
            exc_val:  Wartość wyjątku (None jeśli brak)
            exc_tb:   Traceback wyjątku (None jeśli brak)
        """
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