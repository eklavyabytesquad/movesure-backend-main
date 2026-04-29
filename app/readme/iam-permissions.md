# IAM Permissions API

All endpoints are under `/v1/iam` and require a valid JWT (`Authorization: Bearer <token>`).
Every operation is **company-scoped** — permissions and grants from other companies are never accessible.

---

## Endpoints Overview

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/iam/permissions` | Create a permission |
| `POST` | `/v1/iam/permissions/bulk` | Bulk create permissions |
| `GET` | `/v1/iam/permissions` | List permissions |
| `GET` | `/v1/iam/permissions/{permission_id}` | Get a permission |
| `PATCH` | `/v1/iam/permissions/{permission_id}` | Update a permission |
| `DELETE` | `/v1/iam/permissions/{permission_id}` | Delete a permission |
| `POST` | `/v1/iam/grants` | Grant a permission to a user |
| `POST` | `/v1/iam/grants/bulk` | Bulk grant permissions |
| `GET` | `/v1/iam/grants/company` | List all grants company-wide |
| `GET` | `/v1/iam/grants/user/{user_id}` | List all grants for a user |
| `DELETE` | `/v1/iam/grants/{grant_id}` | Revoke one grant |
| `DELETE` | `/v1/iam/grants/user/{user_id}` | Revoke ALL grants for a user |

---

## Concepts

### Permission
A permission defines **what** can be done, defined by three fields:

| Field | Description | Examples |
|-------|-------------|---------|
| `module` | Feature area | `master`, `staff`, `reports`, `billing` |
| `action` | Operation | `create`, `read`, `update`, `delete`, `export` |
| `scope` | Boundary (optional) | `company`, `branch`, `own` |
| `slug` | Shorthand (optional) | `master:city:create`, `staff:read:branch` |

Recommended slug format: **`module:action:scope`**

### Grant
A grant links a **user** to a **permission**, optionally scoped to a specific branch and with an optional expiry date.

---

## 1. Permissions

### `POST /v1/iam/permissions` — Create a permission

```json
{
  "module":    "master",
  "action":    "create",
  "scope":     "branch",
  "slug":      "master:city:create",
  "branch_id": null,
  "meta":      {},
  "is_active": true
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `module` | string | Yes | Feature area name |
| `action` | string | Yes | `create` / `read` / `update` / `delete` / any custom verb |
| `scope` | string | No | `company`, `branch`, `own`, or custom |
| `slug` | string | No | Must be globally unique if set |
| `branch_id` | UUID | No | Scope this permission to a specific branch |
| `meta` | object | No | Any extra data |
| `is_active` | bool | No | Default `true` |

**201 Created**
```json
{
  "message": "Permission created.",
  "permission": {
    "id":         "perm-uuid-...",
    "company_id": "534b7a1a-...",
    "branch_id":  null,
    "module":     "master",
    "action":     "create",
    "scope":      "branch",
    "slug":       "master:city:create",
    "meta":       {},
    "is_active":  true,
    "created_at": "2026-04-26T10:00:00Z",
    "updated_at": "2026-04-26T10:00:00Z"
  }
}
```

| Error | When |
|-------|------|
| `409 Conflict` | `slug` already exists, or same `module+action+scope` already defined for this company |
| `401 Unauthorized` | Missing/invalid token |

---

### `POST /v1/iam/permissions/bulk` — Bulk create permissions

```json
{
  "items": [
    { "module": "master", "action": "create", "scope": "branch", "slug": "master:city:create" },
    { "module": "master", "action": "read",   "scope": "branch", "slug": "master:city:read"   },
    { "module": "staff",  "action": "create", "scope": "company","slug": "staff:create:company"},
    { "module": "staff",  "action": "read",   "scope": "company","slug": "staff:read:company"  }
  ]
}
```

**201 Created**
```json
{
  "created_count": 3,
  "error_count":   1,
  "created": [ { ... }, { ... }, { ... } ],
  "errors": [
    { "index": 2, "slug": "staff:create:company", "error": "Duplicate slug." }
  ]
}
```

---

### `GET /v1/iam/permissions` — List permissions

| Query param | Type | Description |
|-------------|------|-------------|
| `module` | string | Filter by module (`master`, `staff`, etc.) |
| `branch_id` | UUID | Filter by branch scope |
| `is_active` | bool | `true` / `false` |

**200 OK**
```json
{
  "count": 4,
  "permissions": [
    { "id": "...", "module": "master", "action": "create", "scope": "branch", "slug": "master:city:create", "is_active": true, ... },
    { "id": "...", "module": "master", "action": "read",   "scope": "branch", "slug": "master:city:read",   "is_active": true, ... }
  ]
}
```

---

### `GET /v1/iam/permissions/{permission_id}` — Get a permission

Returns `404` if the permission doesn't belong to your company.

---

### `PATCH /v1/iam/permissions/{permission_id}` — Update a permission

Send only the fields you want to change:

```json
{ "is_active": false }
```

```json
{ "slug": "master:city:create:v2", "meta": { "description": "Create cities in any branch" } }
```

| Error | When |
|-------|------|
| `409 Conflict` | New slug already used by another permission |
| `404 Not Found` | Permission not in your company |

---

### `DELETE /v1/iam/permissions/{permission_id}` — Delete a permission

**Returns `204 No Content`.**
Deleting a permission **cascades** — all user grants for that permission are also removed automatically by the DB.

---

## 2. Grants (Assign / Revoke)

### `POST /v1/iam/grants` — Grant a permission to a user

```json
{
  "user_id":       "user-uuid-...",
  "permission_id": "perm-uuid-...",
  "branch_id":     "758297fc-...",
  "reason":        "Assigned as city manager",
  "expires_at":    "2026-12-31T23:59:59Z"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `user_id` | UUID | Yes | Must belong to your company |
| `permission_id` | UUID | Yes | Must belong to your company |
| `branch_id` | UUID | No | Restricts the grant to a specific branch |
| `reason` | string | No | Audit trail note |
| `expires_at` | ISO 8601 | No | Grant auto-expires (enforced by your app logic) |

**201 Created**
```json
{
  "message": "Permission granted.",
  "grant": {
    "id":            "grant-uuid-...",
    "user_id":       "user-uuid-...",
    "permission_id": "perm-uuid-...",
    "company_id":    "534b7a1a-...",
    "branch_id":     "758297fc-...",
    "reason":        "Assigned as city manager",
    "granted_by":    "admin-uuid-...",
    "expires_at":    "2026-12-31T23:59:59Z",
    "created_at":    "2026-04-26T10:00:00Z"
  }
}
```

| Error | When |
|-------|------|
| `409 Conflict` | User already has this permission |
| `404 Not Found` | `user_id` or `permission_id` not in your company |

---

### `POST /v1/iam/grants/bulk` — Bulk grant permissions

Grant many permissions to one or many users in a single request.

```json
{
  "items": [
    { "user_id": "user-uuid-1", "permission_id": "perm-uuid-A", "reason": "Promoted to manager" },
    { "user_id": "user-uuid-1", "permission_id": "perm-uuid-B" },
    { "user_id": "user-uuid-2", "permission_id": "perm-uuid-A", "branch_id": "758297fc-...", "expires_at": "2026-12-31T23:59:59Z" }
  ]
}
```

**201 Created**
```json
{
  "granted_count": 2,
  "error_count":   1,
  "granted": [ { ... }, { ... } ],
  "errors": [
    { "index": 1, "user_id": "user-uuid-1", "permission_id": "perm-uuid-B", "error": "Already granted." }
  ]
}
```

---

### `GET /v1/iam/grants/company` — All grants company-wide

Returns every user-permission assignment in your company. Filter by branch.

| Query param | Type | Description |
|-------------|------|-------------|
| `branch_id` | UUID | Filter to grants scoped to a specific branch |

**200 OK**
```json
{
  "count": 3,
  "grants": [
    {
      "id":            "grant-uuid-...",
      "user_id":       "user-uuid-1",
      "permission_id": "perm-uuid-A",
      "company_id":    "534b7a1a-...",
      "branch_id":     null,
      "granted_by":    "admin-uuid-...",
      "expires_at":    null,
      "iam_permission": { "id": "...", "module": "master", "action": "create", "scope": "branch", "slug": "master:city:create" }
    }
  ]
}
```

---

### `GET /v1/iam/grants/user/{user_id}` — Grants for a specific user

| Query param | Type | Description |
|-------------|------|-------------|
| `branch_id` | UUID | Filter to branch-scoped grants |
| `active_only` | bool | `true` — exclude grants where the permission is inactive |

**200 OK**
```json
{
  "user_id": "user-uuid-1",
  "count": 2,
  "grants": [
    {
      "id":            "grant-uuid-...",
      "permission_id": "perm-uuid-A",
      "branch_id":     null,
      "expires_at":    null,
      "iam_permission": { "module": "master", "action": "create", "slug": "master:city:create", "is_active": true }
    }
  ]
}
```

---

### `DELETE /v1/iam/grants/{grant_id}` — Revoke one grant

**Returns `204 No Content`.** Removes a single user-permission assignment by its grant ID.

---

### `DELETE /v1/iam/grants/user/{user_id}` — Revoke ALL grants for a user

Removes every permission the user has within your company.

**200 OK**
```json
{
  "message": "Revoked 4 permission(s) for user 'user-uuid-1'.",
  "revoked_count": 4
}
```

---

## Typical Frontend Flow

### Step 1 — Set up permissions (once, on setup)

```js
// Create all permissions your app needs
await fetch('/v1/iam/permissions/bulk', {
  method: 'POST',
  headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({
    items: [
      { module: 'master', action: 'create', scope: 'branch',   slug: 'master:city:create' },
      { module: 'master', action: 'read',   scope: 'branch',   slug: 'master:city:read' },
      { module: 'staff',  action: 'create', scope: 'company',  slug: 'staff:create:company' },
      { module: 'staff',  action: 'read',   scope: 'company',  slug: 'staff:read:company' },
      { module: 'reports',action: 'export', scope: 'company',  slug: 'reports:export:company' },
    ]
  })
});
```

### Step 2 — Assign permissions to a user

```js
// Fetch available permissions
const { permissions } = await fetch('/v1/iam/permissions', {
  headers: { Authorization: `Bearer ${token}` }
}).then(r => r.json());

// Show a multi-select in the UI, then bulk-grant selected ones
await fetch('/v1/iam/grants/bulk', {
  method: 'POST',
  headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({
    items: selectedPermissions.map(perm => ({
      user_id:       targetUserId,
      permission_id: perm.id,
      reason:        'Assigned by admin',
    }))
  })
});
```

### Step 3 — Check permissions on a page load

```js
// Load what a user can do
const { grants } = await fetch(`/v1/iam/grants/user/${userId}?active_only=true`, {
  headers: { Authorization: `Bearer ${token}` }
}).then(r => r.json());

const slugs = new Set(grants.map(g => g.iam_permission?.slug).filter(Boolean));

const canCreateCity  = slugs.has('master:city:create');
const canExportReport = slugs.has('reports:export:company');
```

---

## Quick Test (PowerShell)

```powershell
# 1. Login
$body = '{"email":"alice@techmove.io","password":"Alice@9876"}'
$r    = Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/auth/login" `
          -Method POST -ContentType "application/json" -Body $body -UseBasicParsing | ConvertFrom-Json
$TOKEN   = $r.access_token
$USER_ID = $r.user.id
$H = @{Authorization="Bearer $TOKEN"; "Content-Type"="application/json"}

# 2. Create a permission
$perm = Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/iam/permissions" `
  -Method POST -Headers $H `
  -Body '{"module":"master","action":"create","scope":"branch","slug":"master:city:create"}' `
  -UseBasicParsing | ConvertFrom-Json
$PERM_ID = $perm.permission.id

# 3. List permissions
(Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/iam/permissions" -Headers $H -UseBasicParsing).Content `
  | ConvertFrom-Json | Select-Object -ExpandProperty permissions | Format-Table id, module, action, scope, slug -AutoSize

# 4. Grant permission to a user
$grant = Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/iam/grants" `
  -Method POST -Headers $H `
  -Body (ConvertTo-Json @{user_id=$USER_ID; permission_id=$PERM_ID; reason="Test grant"}) `
  -UseBasicParsing | ConvertFrom-Json
$GRANT_ID = $grant.grant.id

# 5. View user's permissions
(Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/iam/grants/user/$USER_ID" -Headers $H -UseBasicParsing).Content | ConvertFrom-Json

# 6. Revoke a single grant
Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/iam/grants/$GRANT_ID" -Method DELETE -Headers $H -UseBasicParsing

# 7. Bulk grant multiple permissions
$bulkBody = ConvertTo-Json @{
  items = @(
    @{user_id=$USER_ID; permission_id=$PERM_ID; reason="Bulk grant test"}
  )
}
Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/iam/grants/bulk" `
  -Method POST -Headers $H -Body $bulkBody -UseBasicParsing
```
