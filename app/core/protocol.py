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


def encode_command(command: str) -> bytes:
    """Encode remote command payload."""

    return command.strip().lower().encode("utf-8")


def decode_command(data: bytes) -> str:
    """Decode remote command payload."""

    return data.decode("utf-8").strip().lower()
