"""Dedicated authenticated encryption; row/type bound to prevent ciphertext substitution."""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config import get_settings


def cipher():
    raw = get_settings().yellow_cards_key
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise RuntimeError("YELLOW_CARDS_KEY must be base64") from exc
    if len(key) != 32:
        raise RuntimeError("YELLOW_CARDS_KEY must encode 32 bytes")
    return AESGCM(key)


def seal(data: bytes, context: str) -> bytes:
    nonce = os.urandom(12)
    return nonce + cipher().encrypt(nonce, data, context.encode())


def unseal(data: bytes, context: str) -> bytes:
    return cipher().decrypt(data[:12], data[12:], context.encode())
