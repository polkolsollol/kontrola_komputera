"""
Punkt wejscia aplikacji kontroli/podgladu komputera.

Ten plik jest warstwa integracyjna lidera projektu. Nie powinien zawierac
logiki przechwytywania ekranu, sieci ani UI. Jego zadaniem jest uruchomic
wlasciwy tryb i jasno pokazac, ktory modul zespolu jest jeszcze niegotowy.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def _prepare_import_paths() -> None:
    """Pozwala uruchamiac obecne moduly zanim zostana uporzadkowane w pakiety."""
    for directory in (PROJECT_ROOT, PROJECT_ROOT / "core", PROJECT_ROOT / "ui"):
        directory_str = str(directory)
        if directory_str not in sys.path:
            sys.path.insert(0, directory_str)


def run_ui() -> int:
    """Uruchamia aplikacje okienkowa. Obecnie UI korzysta z symulacji klatek."""
    _prepare_import_paths()
    from ui.ui import main as ui_main

    ui_main()
    return 0


def run_sender(host: str, port: int, fps: int, monitor: int, quality: int) -> int:
    """
    Uruchamia komputer wysylajacy ekran.

    Docelowy przeplyw:
    ScreenGrabber -> JPEG FrameData -> NetworkSender -> komputer odbierajacy w LAN.
    """
    _prepare_import_paths()

    try:
        from grabber.screen_grabber import ScreenGrabber
        from network.connection import NetworkSender
    except Exception as exc:  # noqa: BLE001 - integrator ma pokazac czytelny blad.
        print("[main] Tryb sender nie moze wystartowac.")
        print("[main] Modul grabber/server wymaga poprawek przed integracja.")
        print(f"[main] Szczegoly importu: {exc}")
        return 1

    delay = 1 / max(fps, 1)
    grabber = ScreenGrabber(monitor_index=monitor, jpeg_quality=quality)
    sender = NetworkSender(host=host, port=port)

    print(f"[main] Sender: nasluchiwanie na {host}:{port}")
    print("[main] Po polaczeniu klienta rozpocznie sie wysylanie klatek.")

    try:
        grabber.start()
        sender.start()
        while True:
            frame = grabber.get_latest_frame()
            sender.send_frame(frame)
            time.sleep(delay)
    except KeyboardInterrupt:
        print("\n[main] Zatrzymywanie sendera...")
    finally:
        grabber.stop()
        sender.stop()

    return 0


def run_receiver(host: str, port: int) -> int:
    """
    Minimalny tryb testowy odbiorcy bez UI.

    Docelowo ten tryb powinien zostac zastapiony integracja NetworkReceiver
    z PySide6 UI, aby odebrane JPEG-i byly wyswietlane w oknie.
    """
    _prepare_import_paths()

    try:
        from network.connection import NetworkReceiver
    except Exception as exc:  # noqa: BLE001
        print("[main] Tryb receiver nie moze wystartowac.")
        print("[main] Modul server/network wymaga poprawek przed integracja.")
        print(f"[main] Szczegoly importu: {exc}")
        return 1

    receiver = NetworkReceiver(host=host, port=port)
    receiver.connect()
    print(f"[main] Receiver: polaczono z {host}:{port}")
    print("[main] Tryb testowy wypisuje rozmiary odebranych klatek.")

    try:
        while True:
            frame = receiver.receive_frame()
            print(
                f"[main] Klatka: {frame.width}x{frame.height}, "
                f"{len(frame.pixels)} bajtow, ts={frame.timestamp:.3f}"
            )
    except KeyboardInterrupt:
        print("\n[main] Zatrzymywanie receivera...")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aplikacja do przesylania obrazu ekranu w sieci lokalnej."
    )
    parser.add_argument(
        "--mode",
        choices=("ui", "sender", "receiver"),
        default="ui",
        help="Tryb uruchomienia: ui, sender albo receiver. Domyslnie: ui.",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Adres hosta lub IP celu.")
    parser.add_argument("--port", type=int, default=9000, help="Port TCP.")
    parser.add_argument("--fps", type=int, default=15, help="Limit FPS dla sendera.")
    parser.add_argument("--monitor", type=int, default=1, help="Indeks monitora dla mss.")
    parser.add_argument(
        "--quality",
        type=int,
        default=75,
        help="Jakosc JPEG dla przechwytywania ekranu, zakres 0-100.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.mode == "ui":
        return run_ui()
    if args.mode == "sender":
        return run_sender(args.host, args.port, args.fps, args.monitor, args.quality)
    if args.mode == "receiver":
        return run_receiver(args.host, args.port)

    raise ValueError(f"Nieznany tryb: {args.mode}")


if __name__ == "__main__":
    raise SystemExit(main())
