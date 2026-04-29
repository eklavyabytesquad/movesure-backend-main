import os
import secrets
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt
from fastapi import HTTPException, status

from app.services.utils.supabase import get_client
from app.services.iam.service import get_user_by_email, get_user_by_id

logger = logging.getLogger("movesure.auth")

JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS   = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))


# ── Password helpers ──────────────────────────────────────────

def hash_password(password: str) -> str:
    # bcrypt max is 72 bytes — SHA-256 pre-hash removes that limit
    digest = hashlib.sha256(password.encode()).hexdigest().encode()
    return bcrypt.hashpw(digest, bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    digest = hashlib.sha256(plain.encode()).hexdigest().encode()
    return bcrypt.checkpw(digest, hashed.encode())


# ── JWT helpers ───────────────────────────────────────────────

def _make_token(payload: dict, expires_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    return jwt.encode({**payload, "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Login ─────────────────────────────────────────────────────

def _session_device_type(user_agent: str | None) -> str:
    """Map a raw User-Agent to one of the auth_sessions device_type values."""
    if not user_agent:
        return "api"
    ua = user_agent.lower()
    # API tools first — some (PowerShell) include 'Mozilla' in their UA
    if any(k in ua for k in ("powershell", "curl", "postman", "insomnia", "httpx",
                              "python-requests", "python", "okhttp", "retrofit", "aiohttp")):
        return "api"
    if any(k in ua for k in ("android", "iphone", "ipad", "mobile", "cfnetwork")):
        return "mobile"
    if any(k in ua for k in ("mozilla", "chrome", "firefox", "safari", "edg")):
        return "web"
    return "api"


def login(email: str, password: str, ip_address: str | None, user_agent: str | None) -> dict:
    logger.info("login attempt | email=%s ip=%s", email, ip_address)
    db = get_client()
    user = get_user_by_email(email)

    if not user or not verify_password(password, user["password"]):
        logger.warning("login failed | email=%s", email)
        # Record the failed attempt (user_id may be None if email not found)
        try:
            db.table("auth_security_events").insert({
                "user_id":    user["id"] if user else None,
                "event_type": "login_failed",
                "ip_address": ip_address,
                "meta":       {"email": email, "reason": "bad_credentials"},
            }).execute()
        except Exception:
            pass
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    if not user["is_active"]:
        logger.warning("login blocked — inactive | email=%s", email)
        try:
            db.table("auth_security_events").insert({
                "user_id":    user["id"],
                "event_type": "login_failed",
                "ip_address": ip_address,
                "meta":       {"email": email, "reason": "account_inactive"},
            }).execute()
        except Exception:
            pass
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is inactive")

    logger.info("login success | user_id=%s email=%s", user["id"], email)

    # 1. Create session
    device_type = _session_device_type(user_agent)
    session_res = db.table("auth_sessions").insert({
        "user_id":     user["id"],
        "company_id":  user["company_id"],
        "ip_address":  ip_address,
        "user_agent":  user_agent,
        "device_type": device_type,
        "expires_at":  (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    }).execute()
    session = session_res.data[0]

    # 2. Generate access token
    token_payload = {
        "sub":        user["id"],
        "company_id": user["company_id"],
        "branch_id":  user["branch_id"],
        "session_id": session["id"],
        "type":       "access",
    }
    access_token = _make_token(token_payload, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    # 3. Store access token hash (never store raw token)
    db.table("auth_tokens").insert({
        "session_id": session["id"],
        "user_id":    user["id"],
        "type":       "access",
        "token_hash": _sha256(access_token),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).isoformat(),
    }).execute()

    # 4. Generate refresh token (opaque random bytes — NOT a JWT)
    raw_refresh = secrets.token_urlsafe(48)
    db.table("auth_tokens").insert({
        "session_id": session["id"],
        "user_id":    user["id"],
        "type":       "refresh",
        "token_hash": _sha256(raw_refresh),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).isoformat(),
    }).execute()

    # 5. Audit: login success
    db.table("auth_security_events").insert({
        "user_id":    user["id"],
        "session_id": session["id"],
        "event_type": "login_success",
        "ip_address": ip_address,
    }).execute()

    return {
        "access_token":  access_token,
        "refresh_token": raw_refresh,
        "token_type":    "bearer",
        "expires_in":    ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "id":             user["id"],
            "session_id":     session["id"],
            "email":          user["email"],
            "full_name":      user["full_name"],
            "post_in_office": user["post_in_office"],
            "company_id":     user["company_id"],
            "branch_id":      user["branch_id"],
        },
    }


# ── Refresh ───────────────────────────────────────────────────

def refresh_access_token(raw_refresh: str) -> dict:
    """
    Exchange a valid refresh token for a new access token.
    The old refresh token is immediately revoked and a new one issued
    (refresh token rotation — reuse of a revoked token signals theft).
    """
    db = get_client()
    token_hash = _sha256(raw_refresh)

    # Look up the refresh token, join the session for company_id and status
    res = (
        db.table("auth_tokens")
        .select("*, session:auth_sessions(id, company_id, status, expires_at)")
        .eq("token_hash", token_hash)
        .eq("type", "refresh")
        .eq("is_revoked", False)
        .execute()
    )

    if not res.data:
        logger.warning("refresh failed — token not found or already revoked")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")

    record  = res.data[0]
    session = record.get("session")

    # Check token's own expiry
    token_expires = datetime.fromisoformat(record["expires_at"])
    if token_expires.tzinfo is None:
        token_expires = token_expires.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > token_expires:
        logger.warning("refresh failed — token expired for user_id=%s", record["user_id"])
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token expired — please log in again")

    # Check session is still active
    if not session or session.get("status") != "active":
        logger.warning("refresh failed — session revoked/expired for user_id=%s", record["user_id"])
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session has been revoked — please log in again")

    # Check session's own expiry
    session_expires = datetime.fromisoformat(session["expires_at"])
    if session_expires.tzinfo is None:
        session_expires = session_expires.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > session_expires:
        db.table("auth_sessions").update({"status": "expired"}).eq("id", session["id"]).execute()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired — please log in again")

    # Load the user (company-scoped)
    user = get_user_by_id(record["user_id"], session["company_id"])
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    if not user["is_active"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is inactive")

    # ── Rotate: revoke old refresh token ─────────────────────
    db.table("auth_tokens").update({
        "is_revoked": True,
        "revoked_at": datetime.now(timezone.utc).isoformat(),
    }).eq("token_hash", token_hash).execute()

    # ── Issue new access token ────────────────────────────────
    token_payload = {
        "sub":        user["id"],
        "company_id": user["company_id"],
        "branch_id":  user["branch_id"],
        "session_id": session["id"],
        "type":       "access",
    }
    new_access = _make_token(token_payload, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    db.table("auth_tokens").insert({
        "session_id": session["id"],
        "user_id":    user["id"],
        "type":       "access",
        "token_hash": _sha256(new_access),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).isoformat(),
    }).execute()

    # ── Issue new refresh token ───────────────────────────────
    new_raw_refresh = secrets.token_urlsafe(48)
    db.table("auth_tokens").insert({
        "session_id": session["id"],
        "user_id":    user["id"],
        "type":       "refresh",
        "token_hash": _sha256(new_raw_refresh),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).isoformat(),
    }).execute()

    # ── Update session last_active_at ─────────────────────────
    db.table("auth_sessions").update({
        "last_active_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", session["id"]).execute()

    # ── Audit ─────────────────────────────────────────────────
    db.table("auth_security_events").insert({
        "user_id":    user["id"],
        "session_id": session["id"],
        "event_type": "token_refreshed",
    }).execute()

    logger.info("token refreshed | user_id=%s session_id=%s", user["id"], session["id"])

    return {
        "access_token":  new_access,
        "refresh_token": new_raw_refresh,
        "token_type":    "bearer",
        "expires_in":    ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


# ── Logout ────────────────────────────────────────────────────

def logout(raw_refresh: str | None, session_id: str, user_id: str) -> dict:
    """
    Revoke the current session and all its tokens.
    Accepts the raw refresh token for hash-lookup (optional —
    if not provided, revocation still happens via session_id).
    """
    db = get_client()

    # Revoke session
    db.table("auth_sessions").update({
        "status":     "revoked",
        "revoked_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", session_id).execute()

    # Revoke all tokens on this session
    db.table("auth_tokens").update({
        "is_revoked": True,
        "revoked_at": datetime.now(timezone.utc).isoformat(),
    }).eq("session_id", session_id).execute()

    # Audit
    db.table("auth_security_events").insert({
        "user_id":    user_id,
        "session_id": session_id,
        "event_type": "logout",
    }).execute()

    logger.info("logout | user_id=%s session_id=%s", user_id, session_id)
    return {"message": "Logged out successfully"}
