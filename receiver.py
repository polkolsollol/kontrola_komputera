from __future__ import annotations

import argparse

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Odbiornik ekranu z interfejsem graficznym. Uruchom na komputerze podgladu."
    )
    parser.add_argument(
        "--host",
        default="",
        help="Opcjonalny adres IP nadajnika do wpisania przy starcie.",
    )
    parser.add_argument("--port", type=int, default=9000, help="Domyslny port TCP.")
    parser.add_argument(
        "--connect",
        action="store_true",
        help="Automatycznie polacz po uruchomieniu, jesli podano host.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        from app.receiver.ui import run_receiver_ui
    except ModuleNotFoundError as exc:
        print(
            "[receiver] Brakuje zaleznosci Pythona. "
            "Uruchom: pip install -r requirements.txt"
        )
        print(f"[receiver] Szczegoly: {exc}")
        return 1

    return run_receiver_ui(
        initial_host=args.host,
        initial_port=args.port,
        auto_connect=bool(args.connect and args.host),
    )


if __name__ == "__main__":
    raise SystemExit(main())
