import os
import time
import uuid


def uuid7() -> uuid.UUID:
    unix_ms = int(time.time() * 1000)
    rand = os.urandom(10)

    value = bytearray(16)
    value[0:6] = unix_ms.to_bytes(6, "big")
    value[6:16] = rand
    value[6] = (value[6] & 0x0F) | 0x70
    value[8] = (value[8] & 0x3F) | 0x80
    return uuid.UUID(bytes=bytes(value))


def new_id() -> str:
    return str(uuid7())
