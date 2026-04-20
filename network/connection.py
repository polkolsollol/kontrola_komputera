
# network/connection.py

import socket
import struct
from typing import Optional
from core.interfaces import FrameData

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