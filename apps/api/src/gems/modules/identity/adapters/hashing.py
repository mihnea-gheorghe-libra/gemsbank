from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError


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
