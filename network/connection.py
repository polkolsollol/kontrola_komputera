
# network/connection.py

import socket
from typing import Optional

def recv_exact(sock: socket.socket, size: int) -> bytes:
    """Read exactly `size` bytes from TCP socket."""
    buffer = b""
    while len(buffer) < size:
        chunk = sock.recv(size - len(buffer))
        if not chunk:
            raise ConnectionError("Socket closed")
        buffer += chunk
    return buffer