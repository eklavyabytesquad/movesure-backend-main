# Staff Management — API Reference

Base URL (local dev): `http://localhost:8000`  
All endpoints require a valid **JWT access token** (obtained from `/v1/auth/login`).  
Staff are always scoped to the **caller's company** — cross-company access is impossible by design.

---

## Authentication

Every request must include:

```
Authorization: Bearer <access_token>
```

Missing or expired token → `401 Unauthorized`.

---

## Endpoints Overview

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/staff/branches` | List all branches in your company (for dropdowns) |
| `POST` | `/v1/staff` | Add a new staff member to a branch |
| `GET` | `/v1/staff` | List all staff in the company |
| `GET` | `/v1/staff/{user_id}` | Get a single staff member |
| `PATCH` | `/v1/staff/{user_id}` | Update name / role / branch / status / password |

---

## 1. List Branches (for Dropdown)

### `GET /v1/staff/branches`

Call this endpoint **before** rendering the Add Staff form. Use the returned list to build a branch name dropdown — submit the chosen `branch_id` when creating or editing a staff member.

#### Request Headers

| Header | Value | Required |
|--------|-------|----------|
| `Authorization` | `Bearer <token>` | Yes |

#### Success Response — `200 OK`

```json
{
  "company_id": "534b7a1a-828c-4d4c-8746-e3dbc87424a1",
  "count": 2,
  "branches": [
    {
      "branch_id":   "758297fc-c95a-4d15-b869-004c367e45e4",
      "name":        "Main Office",
      "branch_code": "TM001",
      "branch_type": "primary",
      "address":     null,
      "created_at":  "2026-04-25T00:23:05.271Z"
    },
    {
      "branch_id":   "a1b2c3d4-0000-0000-0000-111111111111",
      "name":        "Warehouse North",
      "branch_code": "TM002",
      "branch_type": "branch",
      "address":     "Plot 5, Industrial Area",
      "created_at":  "2026-04-25T09:00:00.000Z"
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `branch_id` | UUID — use this as the value when submitting forms |
| `name` | Human-readable name — display this in the dropdown |
| `branch_code` | Short internal code |
| `branch_type` | `primary`, `hub`, or `branch` |

#### Error Responses

| Status | When | `detail` |
|--------|------|----------|
| `401 Unauthorized` | Missing or invalid token | `"Invalid or expired token"` |

#### Frontend Usage

```js
// Fetch branches for dropdown
const res = await fetch('http://localhost:8000/v1/staff/branches', {
  headers: { 'Authorization': `Bearer ${accessToken}` },
});
const { branches } = await res.json();

// Render dropdown
// branches.map(b => <option value={b.branch_id}>{b.name}</option>)
```

---

## 2. Add Staff Member

### `POST /v1/staff`

Creates a new user account and assigns them to a branch within your company.

#### Request Headers

| Header | Value | Required |
|--------|-------|----------|
| `Content-Type` | `application/json` | Yes |
| `Authorization` | `Bearer <token>` | Yes |

#### Request Body

```json
{
  "full_name":      "Ravi Kumar",
  "email":          "ravi@techmove.io",
  "password":       "Ravi@5678",
  "post_in_office": "driver",
  "branch_id":      "758297fc-c95a-4d15-b869-004c367e45e4",
  "image_url":      null
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `full_name` | string | Yes | Min 2 chars |
| `email` | string | Yes | Must be unique across all users |
| `password` | string | Yes | Min 8 chars — stored as bcrypt hash |
| `post_in_office` | string | Yes | Free text: `driver`, `manager`, `staff`, `accountant`, etc. |
| `branch_id` | UUID | Yes | Must belong to your company |
| `image_url` | string | No | Profile picture URL |

#### Success Response — `201 Created`

```json
{
  "message": "Staff member added successfully.",
  "staff": {
    "id":             "a1b2c3d4-0000-0000-0000-000000000000",
    "email":          "ravi@techmove.io",
    "full_name":      "Ravi Kumar",
    "image_url":      null,
    "post_in_office": "driver",
    "company_id":     "534b7a1a-828c-4d4c-8746-e3dbc87424a1",
    "branch_id":      "758297fc-c95a-4d15-b869-004c367e45e4",
    "is_active":      true,
    "metadata":       {},
    "created_at":     "2026-04-25T08:00:00.000Z",
    "updated_at":     "2026-04-25T08:00:00.000Z"
  }
}
```

> `password` is never returned in any response.

#### Error Responses

| Status | When | `detail` |
|--------|------|----------|
| `401 Unauthorized` | Missing or invalid token | `"Invalid or expired token"` |
| `404 Not Found` | `branch_id` doesn't exist or belongs to another company | `"Branch '...' not found in your company."` |
| `409 Conflict` | Email already registered | `"A user with email '...' already exists."` |
| `422 Unprocessable Entity` | Validation error (short password, bad email, etc.) | `[{"loc": [...], "msg": "..."}]` |

---

## 3. List Staff Members

### `GET /v1/staff`

Returns all staff in the caller's company. Optionally filter by branch.

#### Request Headers

| Header | Value | Required |
|--------|-------|----------|
| `Authorization` | `Bearer <token>` | Yes |

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `branch_id` | UUID | No | Filter results to a specific branch |

#### Examples

```
GET /v1/staff                                          → all staff in the company
GET /v1/staff?branch_id=758297fc-c95a-4d15-b869-...   → only staff in that branch
```

#### Success Response — `200 OK`

```json
{
  "company_id": "534b7a1a-828c-4d4c-8746-e3dbc87424a1",
  "branch_id":  null,
  "count":      2,
  "staff": [
    {
      "id":             "a1b2c3d4-0000-0000-0000-000000000000",
      "email":          "ravi@techmove.io",
      "full_name":      "Ravi Kumar",
      "image_url":      null,
      "post_in_office": "driver",
      "company_id":     "534b7a1a-828c-4d4c-8746-e3dbc87424a1",
      "branch_id":      "758297fc-c95a-4d15-b869-004c367e45e4",
      "is_active":      true,
      "created_at":     "2026-04-25T08:00:00.000Z",
      "updated_at":     "2026-04-25T08:00:00.000Z"
    },
    {
      "id":             "9ce7d074-d634-4b12-8492-bce132b918fb",
      "email":          "alice@techmove.io",
      "full_name":      "Alice Smith",
      "image_url":      null,
      "post_in_office": "super_admin",
      "company_id":     "534b7a1a-828c-4d4c-8746-e3dbc87424a1",
      "branch_id":      "758297fc-c95a-4d15-b869-004c367e45e4",
      "is_active":      true,
      "created_at":     "2026-04-25T00:23:05.518Z",
      "updated_at":     "2026-04-25T00:23:05.518Z"
    }
  ]
}
```

#### Error Responses

| Status | When | `detail` |
|--------|------|----------|
| `401 Unauthorized` | Missing or invalid token | `"Invalid or expired token"` |
| `404 Not Found` | `branch_id` filter doesn't belong to your company | `"Branch '...' not found in your company."` |

---

## 4. Get Single Staff Member

### `GET /v1/staff/{user_id}`

Fetch details of one staff member by their UUID.

#### Request Headers

| Header | Value | Required |
|--------|-------|----------|
| `Authorization` | `Bearer <token>` | Yes |

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `user_id` | UUID | The staff member's ID |

#### Success Response — `200 OK`

```json
{
  "id":             "a1b2c3d4-0000-0000-0000-000000000000",
  "email":          "ravi@techmove.io",
  "full_name":      "Ravi Kumar",
  "image_url":      null,
  "post_in_office": "driver",
  "company_id":     "534b7a1a-828c-4d4c-8746-e3dbc87424a1",
  "branch_id":      "758297fc-c95a-4d15-b869-004c367e45e4",
  "is_active":      true,
  "metadata":       {},
  "created_at":     "2026-04-25T08:00:00.000Z",
  "updated_at":     "2026-04-25T08:00:00.000Z"
}
```

#### Error Responses

| Status | When | `detail` |
|--------|------|----------|
| `401 Unauthorized` | Missing or invalid token | `"Invalid or expired token"` |
| `404 Not Found` | User not found or belongs to another company | `"Staff member not found."` |

---

## 5. Update Staff Member

### `PATCH /v1/staff/{user_id}`

Partially update a staff member. Only the fields you send are changed — all others stay the same.

#### Request Headers

| Header | Value | Required |
|--------|-------|----------|
| `Content-Type` | `application/json` | Yes |
| `Authorization` | `Bearer <token>` | Yes |

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `user_id` | UUID | The staff member's ID |

#### Request Body

All fields are optional — send only what you want to change.

```json
{
  "full_name":      "Ravi Kumar Singh",
  "post_in_office": "manager",
  "branch_id":      "758297fc-c95a-4d15-b869-004c367e45e4",
  "image_url":      "https://cdn.example.com/avatar.jpg",
  "is_active":      false,
  "password":       "NewPass@999"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `full_name` | string | Update display name |
| `post_in_office` | string | Change role/title |
| `branch_id` | UUID | Move to a different branch (must be in same company) |
| `image_url` | string | Update profile picture URL |
| `is_active` | boolean | `false` = deactivate (blocks login), `true` = reactivate |
| `password` | string | Reset password (min 8 chars) |

#### Success Response — `200 OK`

```json
{
  "message": "Staff member updated successfully.",
  "staff": {
    "id":             "a1b2c3d4-0000-0000-0000-000000000000",
    "email":          "ravi@techmove.io",
    "full_name":      "Ravi Kumar Singh",
    "image_url":      "https://cdn.example.com/avatar.jpg",
    "post_in_office": "manager",
    "company_id":     "534b7a1a-828c-4d4c-8746-e3dbc87424a1",
    "branch_id":      "758297fc-c95a-4d15-b869-004c367e45e4",
    "is_active":      false,
    "metadata":       {},
    "created_at":     "2026-04-25T08:00:00.000Z",
    "updated_at":     "2026-04-25T08:30:00.000Z"
  }
}
```

#### Error Responses

| Status | When | `detail` |
|--------|------|----------|
| `401 Unauthorized` | Missing or invalid token | `"Invalid or expired token"` |
| `404 Not Found` | User not found in your company | `"Staff member not found."` |
| `404 Not Found` | New `branch_id` doesn't belong to your company | `"Branch '...' not found in your company."` |
| `422 Unprocessable Entity` | Empty body (no fields provided) | `"No fields provided to update."` |

---

## 6. Quick Test (PowerShell)

```powershell
# 1. Login first to get the token
$login = Invoke-WebRequest -Uri "http://localhost:8000/v1/auth/login" `
  -Method POST -ContentType "application/json" `
  -Body '{"email":"alice@techmove.io","password":"Alice@9876"}' `
  -UseBasicParsing | ConvertFrom-Json
$TOKEN = $login.access_token

# 2. Fetch branches for the dropdown
$branches = (Invoke-WebRequest -Uri "http://localhost:8000/v1/staff/branches" `
  -Headers @{Authorization="Bearer $TOKEN"} -UseBasicParsing).Content | ConvertFrom-Json
$branches.branches | Format-Table branch_id, name, branch_code, branch_type -AutoSize

# Pick the first branch_id from the list
$BRANCH_ID = $branches.branches[0].branch_id

# 2. Add a staff member
$body = "{`"full_name`":`"Ravi Kumar`",`"email`":`"ravi@techmove.io`",`"password`":`"Ravi@5678`",`"post_in_office`":`"driver`",`"branch_id`":`"$BRANCH_ID`"}"
Invoke-WebRequest -Uri "http://localhost:8000/v1/staff" `
  -Method POST -ContentType "application/json" `
  -Headers @{Authorization="Bearer $TOKEN"} `
  -Body $body -UseBasicParsing

# 3. List all staff
Invoke-WebRequest -Uri "http://localhost:8000/v1/staff" `
  -Headers @{Authorization="Bearer $TOKEN"} -UseBasicParsing

# 4. List staff in a specific branch
Invoke-WebRequest -Uri "http://localhost:8000/v1/staff?branch_id=$BRANCH_ID" `
  -Headers @{Authorization="Bearer $TOKEN"} -UseBasicParsing

# 5. Deactivate a staff member  (replace STAFF_ID)
$STAFF_ID = "a1b2c3d4-0000-0000-0000-000000000000"
Invoke-WebRequest -Uri "http://localhost:8000/v1/staff/$STAFF_ID" `
  -Method PATCH -ContentType "application/json" `
  -Headers @{Authorization="Bearer $TOKEN"} `
  -Body '{"is_active":false}' -UseBasicParsing
```

## 7. Quick Test (curl)

```bash
# 1. Login
TOKEN=$(curl -s -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@techmove.io","password":"Alice@9876"}' | jq -r .access_token)

# 2. Fetch branches for the dropdown
curl http://localhost:8000/v1/staff/branches \
  -H "Authorization: Bearer $TOKEN" | jq '.branches[] | {branch_id, name}'

# Pick the branch_id you want
BRANCH_ID="758297fc-c95a-4d15-b869-004c367e45e4"

# 2. Add staff
curl -X POST http://localhost:8000/v1/staff \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"full_name\":\"Ravi Kumar\",\"email\":\"ravi@techmove.io\",\"password\":\"Ravi@5678\",\"post_in_office\":\"driver\",\"branch_id\":\"$BRANCH_ID\"}"

# 3. List all staff
curl http://localhost:8000/v1/staff \
  -H "Authorization: Bearer $TOKEN"

# 4. Deactivate staff  (replace STAFF_ID)
curl -X PATCH http://localhost:8000/v1/staff/STAFF_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'
```

---

## 8. Frontend Integration Notes

```js
// Step 1 — Fetch branches and build dropdown
const { branches } = await fetch('http://localhost:8000/v1/staff/branches', {
  headers: { 'Authorization': `Bearer ${accessToken}` },
}).then(r => r.json());
// branches = [{ branch_id: '...', name: 'Main Office', ... }, ...]
// Render: branches.map(b => <option value={b.branch_id}>{b.name}</option>)

// Step 2 — Add staff using the selected branch_id from the dropdown
const res = await fetch('http://localhost:8000/v1/staff', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    full_name: 'Ravi Kumar',
    email: 'ravi@techmove.io',
    password: 'Ravi@5678',
    post_in_office: 'driver',
    branch_id: branchId,
  }),
});

// List staff (with optional branch filter)
const res = await fetch(`http://localhost:8000/v1/staff?branch_id=${branchId}`, {
  headers: { 'Authorization': `Bearer ${accessToken}` },
});

// Deactivate a staff member
const res = await fetch(`http://localhost:8000/v1/staff/${staffId}`, {
  method: 'PATCH',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({ is_active: false }),
});
```
