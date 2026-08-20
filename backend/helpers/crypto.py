import base64
import hashlib
import logging
import os

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.helpers.context import log_event
from backend.helpers.errors import DomainError

logger = logging.getLogger(__name__)

NONCE_BYTES = 12
KEY_BYTES = 32
DEV_KEY_SEED = b"gems-bank-demo-pin-key"


class CipherError(DomainError):
    code = "cipher_error"
    http_status = 500


class Argon2idHasher:
    def __init__(self) -> None:
        self._hasher = Argon2PasswordHasher()

    def hash(self, secret: str) -> str:
        return self._hasher.hash(secret)

    def verify(self, secret: str, hashed: str) -> bool:
        try:
            return self._hasher.verify(hashed, secret)
        except (VerifyMismatchError, VerificationError):
            return False


def _resolve_key(configured: str | None) -> bytes:
    if not configured:
        log_event(logger, "pin_cipher.dev_key_in_use")
        return hashlib.sha256(DEV_KEY_SEED).digest()
    try:
        key = base64.urlsafe_b64decode(configured)
    except (ValueError, TypeError) as exc:
        raise CipherError("PIN_ENCRYPTION_KEY is not valid base64.") from exc
    if len(key) != KEY_BYTES:
        raise CipherError(f"PIN_ENCRYPTION_KEY must decode to {KEY_BYTES} bytes.")
    return key


class AesGcmPinCipher:
    def __init__(self, configured_key: str | None) -> None:
        self._aead = AESGCM(_resolve_key(configured_key))

    def encrypt(self, plaintext: str, associated_data: str) -> str:
        nonce = os.urandom(NONCE_BYTES)
        sealed = self._aead.encrypt(
            nonce, plaintext.encode("utf-8"), associated_data.encode("utf-8")
        )
        return base64.urlsafe_b64encode(nonce + sealed).decode("ascii")

    def decrypt(self, ciphertext: str, associated_data: str) -> str:
        try:
            blob = base64.urlsafe_b64decode(ciphertext)
        except (ValueError, TypeError) as exc:
            raise CipherError("Stored PIN ciphertext is malformed.") from exc
        if len(blob) <= NONCE_BYTES:
            raise CipherError("Stored PIN ciphertext is malformed.")
        try:
            opened = self._aead.decrypt(
                blob[:NONCE_BYTES], blob[NONCE_BYTES:], associated_data.encode("utf-8")
            )
        except InvalidTag as exc:
            raise CipherError("Stored PIN could not be decrypted with the current key.") from exc
        return opened.decode("utf-8")
