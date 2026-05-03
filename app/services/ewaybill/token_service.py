"""
Masters India JWT Token Manager
--------------------------------
Handles authentication with the Masters India GSP API.

Two-layer cache:
  1. In-memory dict  (_token_cache)  — fastest, lost on process restart
  2. Disk file       (jwt_token.json) — survives restarts

Token lifetime is ~24 h.  A 5-minute early-refresh buffer is applied so
tokens are never used within 5 minutes of expiry.
"""

import os
import json
import base64
import logging
import pathlib
from datetime import datetime, timezone, timedelta

import requests

logger = logging.getLogger("movesure.ewaybill.token")

# ── Masters India credentials (hard-coded per spec; move to .env if needed) ──
MI_USERNAME = os.getenv("MI_USERNAME", "eklavyasingh9870@gmail.com")
MI_PASSWORD = os.getenv("MI_PASSWORD", "3Mw@esRcnk3DM@C")
MI_AUTH_URL = "https://prod-api.mastersindia.co/api/v1/token-auth/"
MI_BASE_URL = "https://prod-api.mastersindia.co/api/v1/"

# ── Token file lives next to this module ────────────────────────────────────
_TOKEN_FILE = pathlib.Path(__file__).parent / "jwt_token.json"

# ── In-memory cache ─────────────────────────────────────────────────────────
_token_cache: dict = {"token": None}


# ────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ────────────────────────────────────────────────────────────────────────────

def _decode_jwt_exp(token: str) -> datetime | None:
    """
    Decode the `exp` claim from a JWT without any external library.
    Returns a timezone-aware UTC datetime, or None on failure.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        # Base64url decode with padding
        payload_b64 = parts[1] + "=="
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes)
        exp_ts = payload.get("exp")
        if exp_ts is None:
            return None
        return datetime.fromtimestamp(int(exp_ts), tz=timezone.utc)
    except Exception as exc:
        logger.warning("JWT decode failed: %s", exc)
        return None


def _is_token_valid(token: str, buffer_minutes: int = 5) -> bool:
    """Return True if the token is present and not expiring within `buffer_minutes`."""
    if not token:
        return False
    exp = _decode_jwt_exp(token)
    if exp is None:
        return False
    cutoff = datetime.now(timezone.utc) + timedelta(minutes=buffer_minutes)
    return exp > cutoff


def _save_token_file(token: str) -> None:
    """Persist token to disk as jwt_token.json."""
    exp = _decode_jwt_exp(token)
    data = {
        "token": token,
        "timestamp": datetime.now().isoformat(),
        "expires_at": exp.isoformat() if exp else None,
        "username": MI_USERNAME,
        "status": "success",
    }
    try:
        _TOKEN_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Token saved to %s (expires %s)", _TOKEN_FILE, data["expires_at"])
    except Exception as exc:
        logger.warning("Could not write jwt_token.json: %s", exc)


def _load_token_file() -> str | None:
    """Read token from disk; return raw token string or None."""
    try:
        if not _TOKEN_FILE.exists():
            return None
        data = json.loads(_TOKEN_FILE.read_text(encoding="utf-8"))
        return data.get("token")
    except Exception as exc:
        logger.warning("Could not read jwt_token.json: %s", exc)
        return None


# ────────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────────

def get_jwt_token() -> str | None:
    """
    Fetch a fresh token from Masters India and persist it in both cache layers.
    Returns the raw token string, or None on failure.
    """
    try:
        resp = requests.post(
            MI_AUTH_URL,
            json={"username": MI_USERNAME, "password": MI_PASSWORD},
            timeout=15,
        )
        resp.raise_for_status()
        token = resp.json().get("token")
        if not token:
            logger.error("Masters India auth response missing 'token' field")
            return None
        _token_cache["token"] = token
        _save_token_file(token)
        logger.info("Masters India JWT token refreshed successfully")
        return token
    except requests.RequestException as exc:
        logger.error("Failed to obtain Masters India token: %s", exc)
        return None


def load_jwt_token() -> str | None:
    """
    Return a valid token using the two-layer cache:
      1. In-memory _token_cache
      2. jwt_token.json on disk
      3. Live refresh via Masters India if both are missing/expired
    """
    # Layer 1 — memory
    mem_token = _token_cache.get("token")
    if mem_token and _is_token_valid(mem_token):
        return mem_token

    # Layer 2 — disk
    file_token = _load_token_file()
    if file_token and _is_token_valid(file_token):
        _token_cache["token"] = file_token
        logger.info("Token restored from disk cache")
        return file_token

    # Layer 3 — live refresh
    logger.info("No valid token in cache; fetching from Masters India...")
    return get_jwt_token()


def get_auth_headers() -> dict:
    """Return HTTP headers dict ready to pass to requests for Masters India calls."""
    token = load_jwt_token()
    if not token:
        raise RuntimeError("Unable to obtain Masters India JWT token")
    return {
        "Authorization": f"JWT {token}",
        "Content-Type": "application/json",
    }


def get_token_status() -> dict:
    """
    Diagnostic: return current token status without triggering a refresh.
    Used by the /ewaybill/token/status endpoint.
    """
    token = _token_cache.get("token") or _load_token_file()
    if not token:
        return {"status": "missing", "token_present": False, "expires_at": None, "valid": False}
    exp = _decode_jwt_exp(token)
    valid = _is_token_valid(token)
    return {
        "status": "valid" if valid else "expired",
        "token_present": True,
        "expires_at": exp.isoformat() if exp else None,
        "valid": valid,
        "username": MI_USERNAME,
    }
