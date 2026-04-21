from __future__ import annotations

import argparse

import receiver
import sender


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Wygodny launcher projektu. Zalecane sa osobne skrypty: sender.py i receiver.py."
    )
    parser.add_argument(
        "role",
        choices=("sender", "receiver"),
        help="Ktory wariant uruchomic.",
    )
    return parser


def main() -> int:
    args, remaining = build_parser().parse_known_args()

    if args.role == "sender":
        sender_args = sender.build_parser().parse_args(remaining)
        return sender.run_sender(
            host=sender_args.host,
            port=sender_args.port,
            monitor=sender_args.monitor,
            fps=sender_args.fps,
            quality=sender_args.quality,
        )

    receiver_args = receiver.build_parser().parse_args(remaining)
    return receiver.run_receiver_ui(
        initial_host=receiver_args.host,
        initial_port=receiver_args.port,
        auto_connect=bool(receiver_args.connect and receiver_args.host),
    )


if __name__ == "__main__":
    raise SystemExit(main())
