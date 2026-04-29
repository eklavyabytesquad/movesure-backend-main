# Onboarding & Login — API Reference

Base URL (local dev): `http://localhost:8000`  
Interactive sandbox: `http://localhost:8000/docs`

All request bodies are **JSON**. All responses are **JSON**.  
Successful responses use `2xx` status codes. Errors return a `detail` field.

---

## 1. Onboard a New Tenant

Register a new company, its first branch, and the super-admin user in a single call.  
This is the **first step** — no auth token required.

### `POST /v1/onboarding/setup`

#### Request Headers

| Header         | Value              | Required |
|----------------|--------------------|----------|
| `Content-Type` | `application/json` | Yes      |

#### Request Body

```json
{
  "company": {
    "name":         "TechMove Ltd",       // required, min 2 chars
    "email":        "admin@techmove.io",  // required, must be unique across all companies
    "plan":         "starter",            // optional
    "address":      "123 Main St",        // optional
    "phone_number": "+91 9876543210",     // optional
    "gstin":        "27AAAAA0000A1Z5"     // optional
  },
  "branch": {
    "name":        "Main Office",         // required, min 2 chars
    "branch_code": "TM001",              // required, min 2 chars — your internal code
    "address":     "123 Main St"          // optional
  },
  "admin": {
    "full_name": "Alice Smith",           // required, min 2 chars
    "email":     "alice@techmove.io",     // required, must be unique across all users
    "password":  "Alice@9876"            // required, min 8 chars
  }
}
```

#### Success Response — `201 Created`

```json
{
  "message": "Tenant onboarded successfully. You can now log in.",
  "company": {
    "company_id":      "534b7a1a-828c-4d4c-8746-e3dbc87424a1",
    "name":            "TechMove Ltd",
    "email":           "admin@techmove.io",
    "address":         null,
    "phone_number":    null,
    "phone_verified":  false,
    "gstin":           null,
    "plan":            "starter",
    "metadata":        {},
    "created_at":      "2026-04-25T00:23:05.232Z",
    "updated_at":      "2026-04-25T00:23:05.232Z",
    "created_by":      null,
    "updated_by":      null
  },
  "branch": {
    "branch_id":   "758297fc-c95a-4d15-b869-004c367e45e4",
    "name":        "Main Office",
    "branch_code": "TM001",
    "branch_type": "primary",
    "company_id":  "534b7a1a-828c-4d4c-8746-e3dbc87424a1",
    "address":     null,
    "metadata":    {},
    "created_at":  "2026-04-25T00:23:05.271Z",
    "updated_at":  "2026-04-25T00:23:05.271Z",
    "created_by":  null,
    "updated_by":  null
  },
  "admin": {
    "id":             "9ce7d074-d634-4b12-8492-bce132b918fb",
    "email":          "alice@techmove.io",
    "full_name":      "Alice Smith",
    "image_url":      null,
    "post_in_office": "super_admin",
    "company_id":     "534b7a1a-828c-4d4c-8746-e3dbc87424a1",
    "branch_id":      "758297fc-c95a-4d15-b869-004c367e45e4",
    "is_active":      true,
    "metadata":       {},
    "created_at":     "2026-04-25T00:23:05.518Z",
    "updated_at":     "2026-04-25T00:23:05.518Z"
  }
}
```

> **Note:** `password` is never returned. The hash is stored internally only.

#### Error Responses

| Status | When | `detail` example |
|--------|------|-----------------|
| `409 Conflict` | Company email already registered | `"A company with email 'admin@techmove.io' already exists."` |
| `409 Conflict` | Admin email already registered | `"A user with email 'alice@techmove.io' already exists."` |
| `422 Unprocessable Entity` | Validation failure (missing field, bad email, password too short) | `[{"loc": ["body", "admin", "password"], "msg": "..."}]` |

#### Frontend Flow

```
1. Collect company, branch, admin details in a registration form
2. POST /v1/onboarding/setup
3. On 201 → save company_id, branch_id, admin.id for display
4. Redirect user to the Login page
5. On 409 → show "Email already registered" error on the relevant field
```

---

## 2. Login

Authenticate an existing user and receive a JWT access token.

### `POST /v1/auth/login`

#### Request Headers

| Header         | Value              | Required |
|----------------|--------------------|----------|
| `Content-Type` | `application/json` | Yes      |

#### Request Body

```json
{
  "email":    "alice@techmove.io",
  "password": "Alice@9876"
}
```

#### Success Response — `200 OK`

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type":   "bearer",
  "expires_in":   1800,
  "user": {
    "id":             "9ce7d074-d634-4b12-8492-bce132b918fb",
    "session_id":     "2dafc7ad-5346-46d7-84c5-afd0ef67e405",
    "email":          "alice@techmove.io",
    "full_name":      "Alice Smith",
    "post_in_office": "super_admin",
    "company_id":     "534b7a1a-828c-4d4c-8746-e3dbc87424a1",
    "branch_id":      "758297fc-c95a-4d15-b869-004c367e45e4"
  }
}
```

| Field | Description |
|-------|-------------|
| `access_token` | JWT — send this in every subsequent API request |
| `token_type` | Always `"bearer"` |
| `expires_in` | Seconds until the token expires (1800 = 30 minutes) |
| `user.id` | User's UUID |
| `user.session_id` | Session UUID — store to support logout / session listing |
| `user.company_id` | Company the user belongs to |
| `user.branch_id` | Branch the user is assigned to |
| `user.post_in_office` | Role: `super_admin`, or future roles added by admin |

#### JWT Payload (decoded)

```json
{
  "sub":        "9ce7d074-d634-4b12-8492-bce132b918fb",
  "company_id": "534b7a1a-828c-4d4c-8746-e3dbc87424a1",
  "branch_id":  "758297fc-c95a-4d15-b869-004c367e45e4",
  "session_id": "2dafc7ad-5346-46d7-84c5-afd0ef67e405",
  "type":       "access",
  "exp":        1745541600
}
```

> **Never decode the JWT on the frontend to make access decisions.** Always rely on the API's `401`/`403` responses. Decoding is only acceptable for reading display values like `full_name`.

#### Error Responses

| Status | When | `detail` |
|--------|------|----------|
| `401 Unauthorized` | Email not found or wrong password | `"Invalid email or password"` |
| `403 Forbidden` | Account exists but has been deactivated | `"Account is inactive"` |
| `422 Unprocessable Entity` | Missing field or invalid email format | `[{"loc": ["body", "email"], "msg": "..."}]` |

> Both "email not found" and "wrong password" return the same `401` message intentionally — this prevents user enumeration attacks.

#### Frontend Flow

```
1. User submits email + password
2. POST /v1/auth/login
3. On 200 → store access_token (e.g. in memory or httpOnly cookie)
         → store user object in app state
         → redirect to dashboard
4. On 401 → show "Invalid email or password"
5. On 403 → show "Your account has been deactivated. Contact support."
```

---

## 3. Using the Token — Authenticated Requests

Include the token from login in every subsequent API request:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Example (fetch):
```js
const res = await fetch('http://localhost:8000/v1/some-endpoint', {
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  }
});
```

Example (axios):
```js
axios.defaults.headers.common['Authorization'] = `Bearer ${accessToken}`;
```

When the token expires (after 30 minutes), the API returns `401 Unauthorized`. The frontend should redirect the user back to the login page.

---

## 4. Token Storage — Security Guidance

| Storage method | Safe? | Notes |
|----------------|-------|-------|
| `httpOnly` cookie | Best | Not accessible to JS — protects against XSS |
| In-memory (JS variable) | Good | Lost on page refresh — use refresh token flow |
| `localStorage` | Avoid | Accessible to any JS on the page — XSS risk |
| `sessionStorage` | Acceptable | Cleared on tab close, still XSS-accessible |

---

## 5. Quick Test (PowerShell)

```powershell
# Onboarding
$body = '{
  "company": {"name": "TechMove Ltd", "email": "admin@techmove.io", "plan": "starter"},
  "branch":  {"name": "Main Office", "branch_code": "TM001"},
  "admin":   {"full_name": "Alice Smith", "email": "alice@techmove.io", "password": "Alice@9876"}
}'
Invoke-WebRequest -Uri "http://localhost:8000/v1/onboarding/setup" `
  -Method POST -ContentType "application/json" -Body $body -UseBasicParsing

# Login
$body = '{"email": "alice@techmove.io", "password": "Alice@9876"}'
Invoke-WebRequest -Uri "http://localhost:8000/v1/auth/login" `
  -Method POST -ContentType "application/json" -Body $body -UseBasicParsing
```

## 6. Quick Test (curl)

```bash
# Onboarding
curl -X POST http://localhost:8000/v1/onboarding/setup \
  -H "Content-Type: application/json" \
  -d '{
    "company": {"name": "TechMove Ltd", "email": "admin@techmove.io", "plan": "starter"},
    "branch":  {"name": "Main Office", "branch_code": "TM001"},
    "admin":   {"full_name": "Alice Smith", "email": "alice@techmove.io", "password": "Alice@9876"}
  }'

# Login
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@techmove.io", "password": "Alice@9876"}'
```
