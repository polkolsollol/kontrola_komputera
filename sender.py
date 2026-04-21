from __future__ import annotations

import argparse
import logging
import time

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Nadajnik ekranu. Uruchom na komputerze, z ktorego ma byc wysylany obraz."
    )
    parser.add_argument("--host", default="0.0.0.0", help="Adres nasluchu TCP.")
    parser.add_argument("--port", type=int, default=9000, help="Port TCP.")
    parser.add_argument("--monitor", type=int, default=1, help="Indeks monitora dla mss.")
    parser.add_argument("--fps", type=int, default=15, help="Docelowy limit FPS przechwytywania.")
    parser.add_argument("--quality", type=int, default=75, help="Jakosc JPEG w zakresie 1-100.")
    return parser


def run_sender(host: str, port: int, monitor: int, fps: int, quality: int) -> int:
    try:
        from grabber.screen_grabber import ScreenGrabber
        from network.connection import NetworkServer
    except ModuleNotFoundError as exc:
        print(
            "[sender] Brakuje zaleznosci Pythona. "
            "Uruchom: pip install -r requirements.txt"
        )
        print(f"[sender] Szczegoly: {exc}")
        return 1

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    server = NetworkServer(host=host, port=port)
    grabber = ScreenGrabber(monitor_index=monitor, jpeg_quality=quality, target_fps=fps)

    try:
        server.start()
        grabber.start()
        print(f"[sender] Nadajnik uruchomiony na {host}:{port}")
        print("[sender] Czekam na polaczenie odbiornika...")

        while True:
            server.accept_client()
            print("[sender] Odbiornik polaczony. Rozpoczynam wysylanie klatek.")
            last_timestamp = None

            while True:
                try:
                    frame = grabber.get_latest_frame()
                except RuntimeError:
                    time.sleep(0.01)
                    continue

                if last_timestamp == frame.timestamp:
                    time.sleep(0.001)
                    continue

                last_timestamp = frame.timestamp
                try:
                    server.send_frame(frame)
                except ConnectionError:
                    print("[sender] Polaczenie zostalo utracone. Oczekiwanie na kolejnego odbiorce...")
                    break
    except KeyboardInterrupt:
        print("\n[sender] Zatrzymywanie nadajnika...")
    finally:
        grabber.stop()
        server.stop()

    return 0


def main() -> int:
    args = build_parser().parse_args()
    return run_sender(
        host=args.host,
        port=args.port,
        monitor=args.monitor,
        fps=args.fps,
        quality=args.quality,
    )


if __name__ == "__main__":
    raise SystemExit(main())
