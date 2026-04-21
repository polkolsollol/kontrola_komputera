from __future__ import annotations

import threading
import time

from core.interfaces import FrameData
from network.connection import NetworkReceiver, NetworkServer


def run_server() -> None:
    server = NetworkServer(host="127.0.0.1", port=9000)
    server.start()
    server.accept_client()
    try:
        frame = FrameData(
            pixels=b"test_pixels",
            width=1920,
            height=1080,
            timestamp=time.time(),
        )
        server.send_frame(frame)
    finally:
        server.stop()


def run_receiver() -> None:
    receiver = NetworkReceiver(host="127.0.0.1", port=9000)
    receiver.connect()
    try:
        frame = receiver.receive_frame()
        print("[receiver] Received frame:", frame)
    finally:
        receiver.stop()


if __name__ == "__main__":
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(1)
    run_receiver()
