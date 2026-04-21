import threading
import time
from network.connection import NetworkServer, NetworkReceiver
from core.interfaces import FrameData

def run_server():
    server = NetworkServer(host="127.0.0.1", port=9000)
    server.start()
    try:
        # Test sending a frame
        frame = FrameData(
            pixels=b"test_pixels",
            width=1920,
            height=1080,
            timestamp=time.time()
        )
        server.send_frame(frame)
    finally:
        server.stop()

def run_receiver():
    receiver = NetworkReceiver(host="127.0.0.1", port=9000)
    receiver.connect()
    try:
        # Test receiving a frame
        frame = receiver.receive_frame()
        print("[Receiver] Received frame:", frame)
    finally:
        receiver.stop()

if __name__ == "__main__":
    # Run server in a separate thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Give the server some time to start
    time.sleep(1)

    # Run receiver
    run_receiver()