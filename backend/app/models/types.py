from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.services import crypto


class EncryptedString(TypeDecorator):
    """String column transparently encrypted with Fernet."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else crypto.encrypt(value)

    def process_result_value(self, value, dialect):
        return None if value is None else crypto.decrypt(value)
