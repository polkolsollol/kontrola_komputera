
# network/connection.py

import socket
import struct
import time
from typing import Optional
from core.interfaces import FrameData
from core.protocol import pack_message, HEADER_SIZE, MSG_TYPE_FRAME

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


class NetworkSender:
    def __init__(self, host="0.0.0.0", port=9000):
        self.host = host
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.client_socket: Optional[socket.socket] = None

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)

        print(f"[Sender] Listening on {self.host}:{self.port}")
        self.client_socket, addr = self.server_socket.accept()
        print(f"[Sender] Client connected: {addr}")

    def send_frame(self, frame: FrameData):
        if not self.client_socket:
            return

        payload = serialize_frame(frame)
        message = pack_message(MSG_TYPE_FRAME, payload)

        try:
            self.client_socket.sendall(message)
        except (BrokenPipeError, ConnectionResetError):
            print("[Sender] Connection lost")
            self.client_socket.close()
            self.client_socket = None

    def stop(self):
        if self.client_socket:
            self.client_socket.close()
        if self.server_socket:
            self.server_socket.close()


class NetworkReceiver:
    def __init__(self, host="127.0.0.1", port=9000, reconnect_delay=2):
        self.host = host
        self.port = port
        self.reconnect_delay = reconnect_delay
        self.socket: Optional[socket.socket] = None

    def connect(self):
        while True:
            try:
                print("[Receiver] Connecting...")
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.connect((self.host, self.port))
                print("[Receiver] Connected")
                return
            except ConnectionRefusedError:
                time.sleep(self.reconnect_delay)

    
    def receive_frame(self) -> FrameData:
        try:
            header = recv_exact(self.socket, HEADER_SIZE)
            data_size, msg_type = struct.unpack("!IB", header)
            payload = recv_exact(self.socket, data_size)
        except (ConnectionError, OSError):
            print("[Receiver] Connection lost, reconnecting...")
            self.socket.close()
            self.connect()
            raise

        if msg_type == MSG_TYPE_FRAME:
            return deserialize_frame(payload)

        raise ValueError(f"Unknown message type: {msg_type}")

