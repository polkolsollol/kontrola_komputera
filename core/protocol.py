from __future__ import annotations

import struct


HEADER_FORMAT = "!IB"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

MSG_TYPE_FRAME = 1
MSG_TYPE_COMMAND = 2


def pack_message(msg_type: int, data: bytes) -> bytes:
    """Pack message as [size:4][type:1][payload]."""

    header = struct.pack(HEADER_FORMAT, len(data), msg_type)
    return header + data


def unpack_header(header: bytes) -> tuple[int, int]:
    """Return payload size and message type."""

    return struct.unpack(HEADER_FORMAT, header)
