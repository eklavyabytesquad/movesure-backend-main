# Frontend Auth & Token Management

## Overview

Authentication is **session-based on the client** — there is no cookie or
`localStorage` involved. Everything lives in `sessionStorage`, which means
data is automatically cleared when the browser tab is closed.

---

## Auth Flow

```
User enters email + password
        │
        ▼
POST /v1/auth/login
        │
   200 OK → { access_token, user }
        │
        ▼
saveAuth(token, user)          ← writes to sessionStorage
        │
        ▼
router.push('/dashboard')
```

On logout / 401:
```
clearAuth()                    ← removes all 3 sessionStorage keys
router.replace('/auth/login')
```

---

## sessionStorage Keys

| Key | Type | Content |
|-----|------|---------|
| `ms_token` | `string` | Raw JWT access token |
| `ms_user` | `JSON string` | Serialised `AuthUser` object |
| `ms_perms` | `JSON string` | Cached permission slugs array |

---

## Core Helpers — `src/lib/auth.ts`

```ts
API_BASE  = 'http://localhost:8000'   // backend base URL

saveAuth(token, user)   // writes ms_token + ms_user
getToken()              // reads ms_token → string | null
getUser()               // reads ms_user  → AuthUser | null
clearAuth()             // removes ms_token, ms_user, ms_perms
```

`getToken()` and `getUser()` both guard against SSR with
`if (typeof window === 'undefined') return null`.

### `AuthUser` shape

```ts
interface AuthUser {
  id:             string;   // staff UUID
  session_id:     string;
  email:          string;
  full_name:      string;
  post_in_office: string;   // 'super_admin' → unrestricted perms
  company_id:     string;
  branch_id:      string;
}
```

---

## How Every Protected Page Guards Itself

Every page/component that calls the API uses the same two-line pattern:

```ts
function tok() {
  const t = getToken();
  if (!t) { router.replace('/auth/login'); return null; }
  return t;
}
```

Then every fetch call:

```ts
const token = tok();
if (!token) return;

fetch(`${API_BASE}/v1/...`, {
  headers: { Authorization: `Bearer ${token}` },
});
```

There is **no global axios interceptor** — each component is responsible for
redirecting on missing token.

---

## Permission System — `src/lib/permissions.ts`

Permissions are fetched once per session from:

```
GET /v1/iam/grants/user/{user.id}?active_only=true
```

The response is parsed into a `Set<string>` of permission slugs and cached in:
1. **In-memory module variable** `_memory` in `usePermissions.ts` — shared
   across all mounted components in the same page lifecycle (avoids N duplicate
   API calls)
2. **`ms_perms`** in `sessionStorage` — survives page navigations within the tab

### Super-admin bypass

If `user.post_in_office === 'super_admin'` **or** the user has zero grants,
`unrestricted = true` is set, which makes `can()` return `true` for everything.

### `usePermissions()` hook

```ts
const { can, canAny, loading, unrestricted } = usePermissions();

can('challan:read:company')           // single slug check
canAny('staff:create:company', '...')  // any-of check
```

While `loading === true` the hook defaults to **allow** (no flicker — items
render, then hide if actually forbidden once grants arrive).

### Invalidating the cache

After granting/revoking permissions call:

```ts
invalidatePermissionsCache()  // from hooks/usePermissions.ts
```

This clears both `_memory` and `ms_perms` so the next page load re-fetches.

---

## Route Guard — `src/components/dashboard/settings/common/route-guard.tsx`

Wraps the entire settings layout. Checks `ROUTE_PERMISSIONS[]` map against the
current pathname:

- Shows a **spinner** while permissions are loading
- Shows a **403 screen** if any required slug is missing
- Passes `children` through if all slugs pass

The guard uses longest-prefix matching — a route like
`/dashboard/settings/challan/books` will match both the root
`/dashboard/settings` (requires `settings:access`) AND
`/dashboard/settings/challan/books` (requires `challan:read:books`), and both
must pass.

---

## Login Page — `src/app/auth/login/page.tsx`

- Calls `POST /v1/auth/login` with `{ email, password }`
- On `200` → `saveAuth(data.access_token, data.user)` → redirect to `/dashboard`
- On `401` → "Invalid email or password"
- On `403` → "Account deactivated"

---

## Security Notes

| Concern | Current behaviour |
|---------|-------------------|
| Token storage | `sessionStorage` — cleared on tab close, not accessible cross-tab |
| Token expiry | No automatic refresh — expired token causes 401, page redirects to login |
| XSS risk | sessionStorage is accessible to JS; no HttpOnly cookie used |
| HTTPS | Assumed in production — `API_BASE` should be `https://` in prod |
| CORS | Handled by FastAPI backend |

---

## Files at a Glance

```
src/lib/auth.ts                          API_BASE, saveAuth, getToken, getUser, clearAuth
src/lib/permissions.ts                   SLUGS enum, loadMyPermissions(), clearPermissionsCache()
src/hooks/usePermissions.ts              usePermissions() hook, invalidatePermissionsCache()
src/app/auth/login/page.tsx              Login form
src/app/auth/register/page.tsx           Registration form
src/components/dashboard/settings/
  common/route-guard.tsx                 Per-route permission gating for settings pages
```
