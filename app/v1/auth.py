from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr

from app.middleware.auth import get_current_user
from app.services.auth.service import (
    login as auth_login,
    refresh_access_token,
    logout as auth_logout,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


# ── Request models ────────────────────────────────────────────

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


# ── Endpoints ─────────────────────────────────────────────────

@router.post("/login", summary="Login and receive access + refresh tokens")
def login(body: LoginRequest, request: Request):
    result = auth_login(
        email=body.email,
        password=body.password,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    request.state.log_user = result["user"]
    return result


@router.post("/refresh", summary="Exchange refresh token for a new access token")
def refresh(body: RefreshRequest):
    """
    Use the refresh token (received at login) to obtain a new access token
    without requiring the user to log in again.

    - The old refresh token is immediately revoked on use (rotation).
    - Returns a new `access_token` and a new `refresh_token`.
    - If the refresh token is expired or revoked, returns 401.
    """
    return refresh_access_token(body.refresh_token)


@router.post("/logout", summary="Revoke session and all tokens")
def logout(body: LogoutRequest, user=Depends(get_current_user)):
    """
    Revoke the current session server-side.
    All tokens (access + refresh) for this session are invalidated.
    The frontend should also clear its local storage after calling this.
    """
    return auth_logout(
        raw_refresh=body.refresh_token,
        session_id=user["session_id"],
        user_id=user["sub"],
    )
