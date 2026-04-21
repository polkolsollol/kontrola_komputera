# network/connection.py

import socket
import struct
import time
import logging
from typing import Optional
from core.interfaces import FrameData
from core.protocol import pack_message, HEADER_SIZE, MSG_TYPE_FRAME

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def recv_exact(sock: socket.socket, size: int) -> bytes:
    """Read exactly `size` bytes from TCP socket."""
    buffer = b""
    while len(buffer) < size:
        chunk = sock.recv(size - len(buffer))
        if not chunk:
            raise ConnectionError("Socket closed")
        buffer += chunk
    return buffer


def serialize_frame(frame: FrameData) -> bytes:
    """
    Format:
    [pixels_len:I][pixels][width:I][height:I][timestamp:d]
    """
    return (
        struct.pack("!I", len(frame.pixels)) +
        frame.pixels +
        struct.pack("!II d", frame.width, frame.height, frame.timestamp)
    )


def deserialize_frame(data: bytes) -> FrameData:
    pixels_len = struct.unpack("!I", data[:4])[0]
    offset = 4

    pixels = data[offset:offset + pixels_len]
    offset += pixels_len

    width, height, timestamp = struct.unpack("!II d", data[offset:offset + 16])

    return FrameData(
        pixels=pixels,
        width=width,
        height=height,
        timestamp=timestamp
    )


class NetworkServer:  # Renamed from NetworkSender
    def __init__(self, host="0.0.0.0", port=9000, timeout=10):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.server_socket: Optional[socket.socket] = None
        self.client_socket: Optional[socket.socket] = None

    def start(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.settimeout(self.timeout)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)

            logging.info(f"[Server] Listening on {self.host}:{self.port}")
            self.client_socket, addr = self.server_socket.accept()
            logging.info(f"[Server] Client connected: {addr}")
        except socket.error as e:
            logging.error(f"[Server] Socket error: {e}")
            self.stop()

    def send_frame(self, frame: FrameData):
        if not self.client_socket:
            logging.warning("[Server] No client connected")
            return

        payload = serialize_frame(frame)
        message = pack_message(MSG_TYPE_FRAME, payload)

        try:
            self.client_socket.sendall(message)
        except (BrokenPipeError, ConnectionResetError) as e:
            logging.error(f"[Server] Connection lost: {e}")
            self.client_socket.close()
            self.client_socket = None

    def stop(self):
        if self.client_socket:
            self.client_socket.close()
        if self.server_socket:
            self.server_socket.close()
        logging.info("[Server] Server stopped")


class NetworkReceiver:
    def __init__(self, host="127.0.0.1", port=9000, reconnect_delay=2, timeout=10):
        self.host = host
        self.port = port
        self.reconnect_delay = reconnect_delay
        self.timeout = timeout
        self.socket: Optional[socket.socket] = None

    def connect(self):
        while True:
            try:
                logging.info("[Receiver] Connecting...")
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(self.timeout)
                self.socket.connect((self.host, self.port))
                logging.info("[Receiver] Connected")
                return
            except (ConnectionRefusedError, socket.timeout) as e:
                logging.warning(f"[Receiver] Connection failed: {e}. Retrying in {self.reconnect_delay}s...")
                time.sleep(self.reconnect_delay)

    def receive_frame(self) -> FrameData:
        try:
            header = recv_exact(self.socket, HEADER_SIZE)
            data_size, msg_type = struct.unpack("!IB", header)
            payload = recv_exact(self.socket, data_size)
        except (ConnectionError, OSError) as e:
            logging.error(f"[Receiver] Connection lost: {e}. Reconnecting...")
            self.socket.close()
            self.connect()
            raise

        if msg_type == MSG_TYPE_FRAME:
            return deserialize_frame(payload)

        raise ValueError(f"Unknown message type: {msg_type}")

    def stop(self):
        if self.socket:
            self.socket.close()
        logging.info("[Receiver] Receiver stopped")