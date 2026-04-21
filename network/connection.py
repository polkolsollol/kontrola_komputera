from __future__ import annotations

import logging
import socket
import struct
from typing import Optional

from core.interfaces import FrameData
from core.protocol import HEADER_SIZE, MSG_TYPE_FRAME, pack_message, unpack_header


LOGGER = logging.getLogger(__name__)
FRAME_META_FORMAT = "!IId"
FRAME_META_SIZE = struct.calcsize(FRAME_META_FORMAT)


def recv_exact(sock: socket.socket, size: int) -> bytes:
    """Read exactly *size* bytes from TCP socket."""

    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise ConnectionError("Socket closed during read")
        chunks.extend(chunk)
    return bytes(chunks)


def serialize_frame(frame: FrameData) -> bytes:
    """Serialize frame as [jpeg_len][jpeg][width][height][timestamp]."""

    return (
        struct.pack("!I", len(frame.pixels))
        + frame.pixels
        + struct.pack(FRAME_META_FORMAT, frame.width, frame.height, frame.timestamp)
    )


def deserialize_frame(data: bytes) -> FrameData:
    """Deserialize frame from bytes created by ``serialize_frame``."""

    if len(data) < 4 + FRAME_META_SIZE:
        raise ValueError("Frame payload is too short")

    pixels_len = struct.unpack("!I", data[:4])[0]
    pixels_end = 4 + pixels_len
    meta_end = pixels_end + FRAME_META_SIZE

    if len(data) < meta_end:
        raise ValueError("Frame payload is truncated")

    pixels = data[4:pixels_end]
    width, height, timestamp = struct.unpack(FRAME_META_FORMAT, data[pixels_end:meta_end])
    return FrameData(pixels=pixels, width=width, height=height, timestamp=timestamp)


class NetworkServer:
    """TCP server used on the sender machine."""

    def __init__(self, host: str = "0.0.0.0", port: int = 9000, timeout: float = 10.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.server_socket: Optional[socket.socket] = None
        self.client_socket: Optional[socket.socket] = None

    def start(self) -> None:
        """Start listening for receiver connection."""

        if self.server_socket is not None:
            return

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen(1)
        self.server_socket = server_socket
        LOGGER.info("Sender listens on %s:%s", self.host, self.port)

    def accept_client(self) -> tuple[str, int]:
        """Wait for a receiver and remember the accepted socket."""

        if self.server_socket is None:
            raise RuntimeError("Server is not started")

        self.close_client()
        client_socket, address = self.server_socket.accept()
        client_socket.settimeout(self.timeout)
        self.client_socket = client_socket
        LOGGER.info("Receiver connected from %s:%s", address[0], address[1])
        return address

    def send_frame(self, frame: FrameData) -> None:
        """Send one frame to currently connected receiver."""

        if self.client_socket is None:
            raise ConnectionError("No receiver connected")

        payload = serialize_frame(frame)
        message = pack_message(MSG_TYPE_FRAME, payload)
        try:
            self.client_socket.sendall(message)
        except OSError as exc:
            self.close_client()
            raise ConnectionError("Failed to send frame") from exc

    def close_client(self) -> None:
        if self.client_socket is not None:
            try:
                self.client_socket.close()
            finally:
                self.client_socket = None

    def stop(self) -> None:
        self.close_client()
        if self.server_socket is not None:
            try:
                self.server_socket.close()
            finally:
                self.server_socket = None


class NetworkReceiver:
    """TCP client used on the viewing machine."""

    def __init__(self, host: str, port: int = 9000, timeout: float = 10.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.socket: Optional[socket.socket] = None

    def connect(self) -> None:
        """Connect to sender."""

        self.stop()
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.settimeout(self.timeout)
        client_socket.connect((self.host, self.port))
        self.socket = client_socket
        LOGGER.info("Connected to sender %s:%s", self.host, self.port)

    def receive_frame(self) -> FrameData:
        """Receive and decode a single frame."""

        if self.socket is None:
            raise RuntimeError("Receiver is not connected")

        header = recv_exact(self.socket, HEADER_SIZE)
        data_size, msg_type = unpack_header(header)
        payload = recv_exact(self.socket, data_size)

        if msg_type != MSG_TYPE_FRAME:
            raise ValueError(f"Unsupported message type: {msg_type}")

        return deserialize_frame(payload)

    def stop(self) -> None:
        if self.socket is not None:
            try:
                self.socket.close()
            finally:
                self.socket = None
