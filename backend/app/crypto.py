import base64, os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def _get_key() -> bytes:
    raw = os.environ.get("CREDENTIAL_ENCRYPTION_KEY")
    if not raw:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY not set")
    return base64.b64decode(raw)

def encrypt_credential(plaintext: str) -> str:
    key = _get_key()
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()

def decrypt_credential(encrypted: str) -> str:
    key = _get_key()
    data = base64.b64decode(encrypted)
    nonce, ct = data[:12], data[12:]
    return AESGCM(key).decrypt(nonce, ct, None).decode()
