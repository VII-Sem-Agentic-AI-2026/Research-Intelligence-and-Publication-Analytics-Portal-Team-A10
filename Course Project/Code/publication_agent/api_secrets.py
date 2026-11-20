"""Persist Gemini credentials using Windows account-bound DPAPI encryption."""

import os
import uuid
import warnings
from pathlib import Path


def key_path(root):
    return Path(root) / "gemini-key.dpapi"


def save_gemini_key(root, key):
    if os.name != "nt":
        raise RuntimeError("Remembering API keys requires Windows on this installation")
    from win32crypt import CryptProtectData
    # Default protection is bound to this Windows user, not machine-wide.
    encrypted = CryptProtectData(key.encode("utf-8"), "Portal Gemini API key", None, None, None, 1)
    path = key_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_bytes(encrypted)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def forget_gemini_key(root):
    key_path(root).unlink(missing_ok=True)


def restore_gemini_key(root):
    if os.environ.get("GEMINI_API_KEY", "").strip():
        return True
    path = key_path(root)
    if not path.exists():
        return False
    try:
        from win32crypt import CryptUnprotectData
        _, decrypted = CryptUnprotectData(path.read_bytes(), None, None, None, 1)
        key = decrypted.decode("utf-8").strip()
        if not key:
            raise ValueError("Empty credential")
    except Exception:
        warnings.warn("The saved Gemini key could not be unlocked. Use Configure AI to save it again.", RuntimeWarning)
        return False
    os.environ["GEMINI_API_KEY"] = key
    return True
