# Auth Management — Issues, Root Causes & Fix Plan

## TL;DR — Why Users Get Logged Out in ~2 Minutes

There are **three compounding problems**, all independent:

| # | Problem | Where | Severity |
|---|---------|-------|----------|
| 1 | `ACCESS_TOKEN_EXPIRE_MINUTES` env var is set too low | Backend `.env` | 🔴 Critical |
| 2 | No refresh token — backend never issues one, frontend can't renew | Backend + Frontend | 🔴 Critical |
| 3 | `sessionStorage` clears on new tab / window | Frontend | 🟡 Medium |

---

## Problem 1 — Token Expires Too Fast

### What happens

`app/services/auth/service.py`:
```python
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
```

The **default** is 30 minutes. But if your `.env` file has:
```
ACCESS_TOKEN_EXPIRE_MINUTES=2
```
…then every token dies after 2 minutes of being issued — not 2 minutes of
inactivity, but 2 minutes after login regardless of what the user does.

### Fix — immediate (stop the bleeding)

Set a sane value in your `.env`:
```
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

For a logistics dashboard that users keep open for hours, 60 minutes is a
reasonable short-term fix while you implement proper refresh (see Problem 2).

> ⚠️ Making the token last longer without a refresh mechanism is a partial
> fix only. A stolen token now lives longer too. Implement refresh (below).

---

## Problem 2 — No Refresh Token (the real architectural gap)

### What happens

The backend creates an `auth_sessions` row with `expires_at = now + 30 days`
at login — but that session record is **never used again**.  There is no
endpoint to trade the session for a new access token.

The frontend has no silent-refresh code either:
```md
> No automatic refresh — expired token causes 401, page redirects to login
```
So when the short-lived access token dies, the user sees a blank page and
gets kicked to `/auth/login`.

### Backend fix — add a refresh token

#### Step 1 — Issue a refresh token at login

In `app/services/auth/service.py`, inside `login()`, after creating the session:

```python
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

# Generate refresh token (long-lived, opaque)
import secrets
raw_refresh = secrets.token_urlsafe(48)   # 64-char URL-safe string

db.table("auth_tokens").insert({
    "session_id": session["id"],
    "user_id":    user["id"],
    "type":       "refresh",
    "token_hash": _sha256(raw_refresh),
    "expires_at": (datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).isoformat(),
}).execute()

return {
    "access_token":  access_token,
    "refresh_token": raw_refresh,          # ← add this
    "token_type":    "bearer",
    "expires_in":    ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    ...
}
```

#### Step 2 — Add `POST /v1/auth/refresh` endpoint

```python
# app/v1/auth.py
@router.post("/auth/refresh")
def api_refresh(body: RefreshRequest):
    """
    Exchange a valid refresh token for a new access token.
    Refresh token is rotated on every use (old one invalidated).
    """
    return auth_service.refresh_token(body.refresh_token)
```

Service logic (`app/services/auth/service.py`):
```python
def refresh_token(raw_refresh: str) -> dict:
    db = get_client()
    token_hash = _sha256(raw_refresh)

    # Look up the refresh token
    res = db.table("auth_tokens") \
        .select("*, auth_sessions(*)") \
        .eq("token_hash", token_hash) \
        .eq("type", "refresh") \
        .execute()

    if not res.data:
        raise HTTPException(401, "Invalid refresh token")

    record = res.data[0]

    # Check expiry
    expires_at = datetime.fromisoformat(record["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(401, "Refresh token expired — please log in again")

    session = record["auth_sessions"]
    if not session or not session.get("is_active", True):
        raise HTTPException(401, "Session has been revoked")

    # Load user
    user = get_user_by_id(record["user_id"])
    if not user or not user["is_active"]:
        raise HTTPException(403, "Account inactive")

    # Issue new access token
    token_payload = {
        "sub":        user["id"],
        "company_id": user["company_id"],
        "branch_id":  user["branch_id"],
        "session_id": session["id"],
        "type":       "access",
    }
    new_access = _make_token(token_payload, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    # Rotate refresh token (invalidate old, issue new)
    db.table("auth_tokens").update({"is_active": False}).eq("token_hash", token_hash).execute()
    new_raw_refresh = secrets.token_urlsafe(48)
    db.table("auth_tokens").insert({
        "session_id": session["id"],
        "user_id":    user["id"],
        "type":       "refresh",
        "token_hash": _sha256(new_raw_refresh),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).isoformat(),
    }).execute()

    # Store new access token hash
    db.table("auth_tokens").insert({
        "session_id": session["id"],
        "user_id":    user["id"],
        "type":       "access",
        "token_hash": _sha256(new_access),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).isoformat(),
    }).execute()

    return {
        "access_token":  new_access,
        "refresh_token": new_raw_refresh,
        "expires_in":    ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }
```

### Frontend fix — silent refresh

#### Step 1 — Store both tokens

Update `src/lib/auth.ts`:
```ts
export const KEYS = {
  TOKEN:   'ms_token',
  REFRESH: 'ms_refresh',    // ← new
  USER:    'ms_user',
  PERMS:   'ms_perms',
  EXPIRY:  'ms_token_exp',  // ← new: store expiry timestamp (ms)
};

export function saveAuth(token: string, refreshToken: string, user: AuthUser, expiresIn: number) {
  sessionStorage.setItem(KEYS.TOKEN,   token);
  sessionStorage.setItem(KEYS.REFRESH, refreshToken);
  sessionStorage.setItem(KEYS.USER,    JSON.stringify(user));
  // Store expiry as Unix ms timestamp
  sessionStorage.setItem(KEYS.EXPIRY,  String(Date.now() + expiresIn * 1000));
}

export function getRefreshToken(): string | null {
  if (typeof window === 'undefined') return null;
  return sessionStorage.getItem(KEYS.REFRESH);
}

export function clearAuth() {
  [KEYS.TOKEN, KEYS.REFRESH, KEYS.USER, KEYS.PERMS, KEYS.EXPIRY].forEach(k =>
    sessionStorage.removeItem(k)
  );
}

export function tokenExpiresAt(): number {
  const v = sessionStorage.getItem(KEYS.EXPIRY);
  return v ? parseInt(v) : 0;
}
```

#### Step 2 — Create a central `apiFetch` wrapper

Create `src/lib/api.ts`:
```ts
import { API_BASE, getToken, getRefreshToken, saveAuth, clearAuth, getUser, tokenExpiresAt } from './auth';

let _refreshPromise: Promise<string> | null = null;  // deduplicate concurrent refreshes

async function doRefresh(): Promise<string> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) throw new Error('no refresh token');

  const res = await fetch(`${API_BASE}/v1/auth/refresh`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!res.ok) throw new Error('refresh failed');

  const data = await res.json();
  const user = getUser()!;
  saveAuth(data.access_token, data.refresh_token, user, data.expires_in);
  return data.access_token;
}

async function getValidToken(): Promise<string | null> {
  const token = getToken();
  if (!token) return null;

  // Proactively refresh if token expires within 60 seconds
  const msUntilExpiry = tokenExpiresAt() - Date.now();
  if (msUntilExpiry < 60_000) {
    try {
      // Deduplicate: if a refresh is already in flight, wait for it
      if (!_refreshPromise) {
        _refreshPromise = doRefresh().finally(() => { _refreshPromise = null; });
      }
      return await _refreshPromise;
    } catch {
      clearAuth();
      return null;
    }
  }

  return token;
}

export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = await getValidToken();

  if (!token) {
    // Redirect to login — use window.location so it works outside React context too
    window.location.replace('/auth/login');
    throw new Error('unauthenticated');
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
      Authorization: `Bearer ${token}`,
    },
  });

  // Handle 401 — token may have just expired on the server side (clock drift, revoke)
  if (res.status === 401) {
    try {
      if (!_refreshPromise) {
        _refreshPromise = doRefresh().finally(() => { _refreshPromise = null; });
      }
      const newToken = await _refreshPromise;

      // Retry the original request once with the new token
      return fetch(`${API_BASE}${path}`, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
          Authorization: `Bearer ${newToken}`,
        },
      });
    } catch {
      clearAuth();
      window.location.replace('/auth/login');
      throw new Error('unauthenticated');
    }
  }

  return res;
}
```

#### Step 3 — Replace raw `fetch` calls in components

Before:
```ts
const res = await fetch(`${API_BASE}/v1/challan`, {
  headers: { Authorization: `Bearer ${token}` },
});
```

After:
```ts
import { apiFetch } from '@/lib/api';

const res = await apiFetch('/v1/challan');
```

All token management, proactive refresh, and 401 handling is handled in one
place. Components no longer need the `tok()` pattern.

#### Step 4 — Update login page

```ts
// src/app/auth/login/page.tsx
const data = await res.json();
saveAuth(data.access_token, data.refresh_token, data.user, data.expires_in);
router.push('/dashboard');
```

---

## Problem 3 — `sessionStorage` Clears on New Tab

### What happens

`sessionStorage` is **tab-isolated by design** in all browsers.
Opening `Ctrl+T` → new tab → `getToken()` returns `null` → redirect to login.

This is less critical than the above but annoying in daily use.

### Options (pick one)

| Option | Tradeoff |
|--------|----------|
| **`localStorage`** | Persists across tabs and browser restarts. Slightly higher XSS risk (no HttpOnly). Acceptable for an internal logistics app on a private network. |
| **BroadcastChannel sync** | Keep `sessionStorage` as primary but broadcast auth state to new tabs from existing ones. Complex, but keeps the "clears on close" property. |
| **HttpOnly cookie** | Most secure. Requires backend to set `Set-Cookie` instead of returning a token. Bigger backend change. |

**Recommended for this app:** Switch to `localStorage`. The app is used by
internal staff on company devices, not public users. The security tradeoff
is acceptable. Change all `sessionStorage` calls in `src/lib/auth.ts` to
`localStorage`.

---

## Summary — Priority Order

### Do now (takes 5 minutes, stops the bleeding)
```
1. Set ACCESS_TOKEN_EXPIRE_MINUTES=60 in backend .env
```

### Do this week (proper fix)
```
2. Backend: add refresh token issuance to login()
3. Backend: add POST /v1/auth/refresh endpoint
4. Frontend: update auth.ts to store refresh token + expiry timestamp
5. Frontend: create src/lib/api.ts with apiFetch()
6. Frontend: replace raw fetch calls with apiFetch()
7. Frontend: switch sessionStorage → localStorage
```

### Recommended token lifetimes after implementing refresh

| Token | Lifetime | Why |
|-------|----------|-----|
| Access token | 15–30 min | Short window if stolen |
| Refresh token | 30 days | Matches existing session expiry |
| Auto-refresh trigger | 60 sec before expiry | Invisible to user |

---

## Current vs Target Architecture

```
CURRENT (broken)
────────────────
login → access_token (2 min) → stored in sessionStorage
         │
         └─ expires → 401 on any API call → redirect to /login
                      ↑ user loses work, session gone

TARGET (correct)
────────────────
login → access_token (15 min) + refresh_token (30 days)
         │                              │
         │                              └─ stored in localStorage
         └─ stored in localStorage         (survives new tabs)
         
Every API call via apiFetch():
  ├─ token expiring in < 60s? → silently call /auth/refresh first
  ├─ 401 from server?         → try /auth/refresh once, retry request
  └─ refresh fails?           → clearAuth() + redirect to /login
```

---

## Files to Create / Modify

| File | Action |
|------|--------|
| `.env` | Set `ACCESS_TOKEN_EXPIRE_MINUTES=60` immediately |
| `app/services/auth/service.py` | Issue refresh token in `login()`, add `refresh_token()` function |
| `app/v1/auth.py` | Add `POST /auth/refresh` endpoint |
| `src/lib/auth.ts` | Add `saveAuth` refresh param, `getRefreshToken()`, `tokenExpiresAt()`, `clearAuth` update, switch to `localStorage` |
| `src/lib/api.ts` | **Create** — central `apiFetch()` with silent refresh |
| `src/app/auth/login/page.tsx` | Pass `refresh_token` and `expires_in` to `saveAuth` |
| All components with `fetch(...)` | Replace with `apiFetch(...)` from `src/lib/api.ts` |
