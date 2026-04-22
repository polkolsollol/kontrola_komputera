from __future__ import annotations

import struct


HEADER_FORMAT = "!IB"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

# Typy wiadomości
MSG_TYPE_FRAME = 1
MSG_TYPE_COMMAND = 2

# Komendy (przesyłane jako payload w MSG_TYPE_COMMAND)
CMD_LOCK = b"LOCK"
CMD_UNLOCK = b"UNLOCK"


def pack_message(msg_type: int, data: bytes) -> bytes:
    """Pack message as [size:4][type:1][payload]."""
    header = struct.pack(HEADER_FORMAT, len(data), msg_type)
    return header + data


def unpack_header(header: bytes) -> tuple[int, int]:
    """Return payload size and message type."""
    return struct.unpack(HEADER_FORMAT, header)


# ---------------------------------------------------------------------------
# Helpery do komend
# ---------------------------------------------------------------------------

def pack_command(command: bytes) -> bytes:
    """Zapakuj komendę (np. CMD_LOCK) jako gotową wiadomość do wysłania."""
    return pack_message(MSG_TYPE_COMMAND, command)


def unpack_command(payload: bytes) -> str:
    """Rozpakuj payload komendy do stringa (np. 'LOCK', 'UNLOCK')."""
    return payload.decode("utf-8")