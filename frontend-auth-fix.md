# Frontend Auth Fix — Implementation Guide

> Backend is updated. Copy-paste each section into the correct file.

---

## What Changed on the Backend

| Endpoint | Change |
|----------|--------|
| `POST /v1/auth/login` | Now also returns `refresh_token` in the response |
| `POST /v1/auth/refresh` | **New** — exchange refresh token for new access + refresh tokens |
| `POST /v1/auth/logout` | **New** — revoke session server-side |

Login response now looks like:
```json
{
  "access_token":  "eyJ...",
  "refresh_token": "abc123...",
  "token_type":    "bearer",
  "expires_in":    1800,
  "user": { ... }
}
```

---

## Step 1 — Replace `src/lib/auth.ts`

Replace the entire file with this:

```ts
// src/lib/auth.ts

export const API_BASE = 'http://localhost:8000'   // change to https:// in production

const KEYS = {
  TOKEN:   'ms_token',
  REFRESH: 'ms_refresh',
  EXPIRY:  'ms_token_exp',   // Unix ms timestamp when access token expires
  USER:    'ms_user',
  PERMS:   'ms_perms',
} as const

export interface AuthUser {
  id:             string
  session_id:     string
  email:          string
  full_name:      string
  post_in_office: string
  company_id:     string
  branch_id:      string
}

// ── Write ──────────────────────────────────────────────────────────────────

export function saveAuth(
  token: string,
  refreshToken: string,
  user: AuthUser,
  expiresIn: number       // seconds (backend sends expires_in)
) {
  localStorage.setItem(KEYS.TOKEN,   token)
  localStorage.setItem(KEYS.REFRESH, refreshToken)
  localStorage.setItem(KEYS.USER,    JSON.stringify(user))
  localStorage.setItem(KEYS.EXPIRY,  String(Date.now() + expiresIn * 1000))
}

export function clearAuth() {
  Object.values(KEYS).forEach(k => localStorage.removeItem(k))
}

// ── Read ───────────────────────────────────────────────────────────────────

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(KEYS.TOKEN)
}

export function getRefreshToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(KEYS.REFRESH)
}

export function getUser(): AuthUser | null {
  if (typeof window === 'undefined') return null
  const raw = localStorage.getItem(KEYS.USER)
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

export function tokenExpiresAt(): number {
  const v = localStorage.getItem(KEYS.EXPIRY)
  return v ? parseInt(v, 10) : 0
}

export function isLoggedIn(): boolean {
  return !!getToken() && !!getUser()
}
```

**Key changes from old version:**
- `sessionStorage` → `localStorage` (survives new tabs and page refresh)
- `saveAuth()` now takes `refreshToken` and `expiresIn` as extra params
- Added `getRefreshToken()`, `tokenExpiresAt()`, `isLoggedIn()`
- `clearAuth()` removes all 5 keys including the new ones

---

## Step 2 — Create `src/lib/api.ts` (new file)

Create this file. It is the **only place** that makes API calls — all components import from here instead of calling `fetch` directly.

```ts
// src/lib/api.ts

import {
  API_BASE,
  getToken,
  getRefreshToken,
  saveAuth,
  clearAuth,
  getUser,
  tokenExpiresAt,
} from './auth'

// One in-flight refresh at a time — all concurrent callers share the same promise
let _refreshPromise: Promise<string> | null = null

async function doRefresh(): Promise<string> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) throw new Error('no_refresh_token')

  const res = await fetch(`${API_BASE}/v1/auth/refresh`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ refresh_token: refreshToken }),
  })

  if (!res.ok) throw new Error('refresh_failed')

  const data = await res.json()
  const user = getUser()!
  // Store the new token pair (expiresIn is in seconds)
  saveAuth(data.access_token, data.refresh_token, user, data.expires_in)
  return data.access_token
}

async function getValidToken(): Promise<string | null> {
  const token = getToken()
  if (!token) return null

  // Proactively refresh if token expires within the next 60 seconds
  const msLeft = tokenExpiresAt() - Date.now()
  if (msLeft < 60_000) {
    try {
      if (!_refreshPromise) {
        _refreshPromise = doRefresh().finally(() => { _refreshPromise = null })
      }
      return await _refreshPromise
    } catch {
      clearAuth()
      return null
    }
  }

  return token
}

/**
 * Use this instead of fetch() for every API call.
 *
 * Usage:
 *   const res = await apiFetch('/v1/challan')
 *   const res = await apiFetch('/v1/challan', { method: 'POST', body: JSON.stringify(data) })
 *
 * - Automatically injects Authorization header
 * - Proactively refreshes token 60 seconds before expiry
 * - On 401: tries one refresh then retries the request
 * - On refresh failure: clears auth and redirects to /auth/login
 */
export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = await getValidToken()

  if (!token) {
    window.location.replace('/auth/login')
    throw new Error('unauthenticated')
  }

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
    Authorization: `Bearer ${token}`,
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })

  if (res.status === 401) {
    // Token may have just expired server-side (clock drift, forced revoke)
    try {
      if (!_refreshPromise) {
        _refreshPromise = doRefresh().finally(() => { _refreshPromise = null })
      }
      const newToken = await _refreshPromise

      // Retry the original request once with the new token
      return fetch(`${API_BASE}${path}`, {
        ...options,
        headers: { ...headers, Authorization: `Bearer ${newToken}` },
      })
    } catch {
      clearAuth()
      window.location.replace('/auth/login')
      throw new Error('unauthenticated')
    }
  }

  return res
}
```

---

## Step 3 — Update Login Page

In `src/app/auth/login/page.tsx`, find the success handler after the login `fetch` call and update it:

**Before:**
```ts
const data = await res.json()
saveAuth(data.access_token, data.user)
router.push('/dashboard')
```

**After:**
```ts
const data = await res.json()
saveAuth(data.access_token, data.refresh_token, data.user, data.expires_in)
router.push('/dashboard')
```

The login `fetch` call itself doesn't need to change (it doesn't need `apiFetch` since the user isn't authenticated yet).

---

## Step 4 — Add Logout Function

Wherever you currently have your logout button/action, replace the `clearAuth()` call with this:

```ts
import { apiFetch } from '@/lib/api'
import { getRefreshToken, clearAuth } from '@/lib/auth'
import { useRouter } from 'next/navigation'

async function handleLogout() {
  try {
    // Tell the backend to revoke the session
    await apiFetch('/v1/auth/logout', {
      method: 'POST',
      body:   JSON.stringify({ refresh_token: getRefreshToken() }),
    })
  } catch {
    // Continue with local logout even if the server call fails
  }
  clearAuth()
  router.replace('/auth/login')
}
```

---

## Step 5 — Replace All `fetch` Calls in Components

This is the most work but it's mechanical. For every component that calls the API:

**Before:**
```ts
const token = getToken()
if (!token) { router.replace('/auth/login'); return }

const res = await fetch(`${API_BASE}/v1/some-endpoint`, {
  headers: { Authorization: `Bearer ${token}` },
})
```

**After:**
```ts
import { apiFetch } from '@/lib/api'

const res = await apiFetch('/v1/some-endpoint')
```

For POST/PATCH/DELETE:
```ts
// Before
const res = await fetch(`${API_BASE}/v1/challan`, {
  method:  'POST',
  headers: {
    'Content-Type':  'application/json',
    Authorization:   `Bearer ${token}`,
  },
  body: JSON.stringify(payload),
})

// After
const res = await apiFetch('/v1/challan', {
  method: 'POST',
  body:   JSON.stringify(payload),
})
```

The `tok()` helper pattern is no longer needed. Remove it from components as you migrate.

---

## Step 6 — Update `usePermissions.ts` (if it uses raw fetch)

If `loadMyPermissions()` in `src/lib/permissions.ts` or `src/hooks/usePermissions.ts` makes a raw `fetch` call to `/v1/iam/grants/user/...`, update it to use `apiFetch` too:

```ts
import { apiFetch } from '@/lib/api'

// replace:
const res = await fetch(`${API_BASE}/v1/iam/grants/user/${user.id}?active_only=true`, {
  headers: { Authorization: `Bearer ${token}` }
})

// with:
const res = await apiFetch(`/v1/iam/grants/user/${user.id}?active_only=true`)
```

---

## Summary of File Changes

| File | Action | What to do |
|------|--------|-----------|
| `src/lib/auth.ts` | Replace | Full replacement from Step 1 |
| `src/lib/api.ts` | Create new | Paste from Step 2 |
| `src/app/auth/login/page.tsx` | Edit | Update `saveAuth(...)` call — Step 3 |
| Logout button/page | Edit | Use `handleLogout()` pattern — Step 4 |
| All components with `fetch(...)` | Edit | Replace with `apiFetch(...)` — Step 5 |
| `src/lib/permissions.ts` or `usePermissions.ts` | Edit | If it uses raw fetch, update — Step 6 |

---

## Token Lifetimes (After This Fix)

| Token | Lifetime set in backend `.env` | Notes |
|-------|------|-------|
| Access token | `ACCESS_TOKEN_EXPIRE_MINUTES=30` | Short-lived; auto-renewed silently |
| Refresh token | `REFRESH_TOKEN_EXPIRE_DAYS=30` | Long-lived; rotated on every use |
| Auto-refresh trigger | 60 seconds before expiry | User sees nothing |

---

## How It Now Works

```
User logs in
  → receives access_token (30 min) + refresh_token (30 days)
  → both stored in localStorage

User makes any API call via apiFetch()
  ├─ token has > 60s left?  → use it directly
  ├─ token has < 60s left?  → silently call /auth/refresh first, then proceed
  └─ server returns 401?    → try /auth/refresh once, retry, if fails → /login

User opens new tab
  → localStorage is shared across tabs → still logged in ✅

User closes browser, reopens
  → localStorage persists → still logged in ✅

Refresh token expires (after 30 days of no login)
  → /auth/refresh returns 401 → clearAuth() → redirect to /login ✅
```
