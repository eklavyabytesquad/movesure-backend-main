# Branch Management

## Migration

Run [app/database/migrations/015_branch_extra_fields.sql](../database/migrations/015_branch_extra_fields.sql) in Supabase SQL editor before using the new fields.

```sql
ALTER TABLE tenant_branches
    ADD COLUMN IF NOT EXISTS mobile_number  VARCHAR(20),
    ADD COLUMN IF NOT EXISTS owner_name     VARCHAR(255),
    ADD COLUMN IF NOT EXISTS city_id        UUID REFERENCES master_city(city_id) ON DELETE SET NULL;
```

---

## Endpoints

| Method | URL | Description |
|--------|-----|-------------|
| `GET`   | `/v1/staff/branches`              | List all branches in company |
| `GET`   | `/v1/staff/branches/{branch_id}`  | Get single branch |
| `POST`  | `/v1/staff/branches`              | Create a new branch |
| `PATCH` | `/v1/staff/branches/{branch_id}`  | Update branch details |

All endpoints require a valid JWT (`Authorization: Bearer <token>`).
`company_id` is always taken from the JWT — you cannot create branches for another company.

---

## Create Branch

```
POST /v1/staff/branches
```

```json
{
  "name":          "Mumbai HO",
  "branch_code":   "MUM-HO",
  "branch_type":   "branch",
  "address":       "123 Link Road, Andheri, Mumbai",
  "mobile_number": "9876543210",
  "owner_name":    "Rajesh Gupta",
  "city_id":       "f416e290-b5c1-47d3-a4e3-fe174a99540f",
  "metadata":      {}
}
```

**Field reference:**

| Field | Required | Values | Notes |
|-------|----------|--------|-------|
| `name` | ✅ | string | Branch display name |
| `branch_code` | ✅ | string (2–50 chars) | Short unique code within company e.g. `MUM-HO` |
| `branch_type` | | `"primary"` \| `"hub"` \| `"branch"` | Defaults to `"branch"` |
| `address` | | string | Full address |
| `mobile_number` | | string | Contact number for this branch |
| `owner_name` | | string | Branch owner / manager name |
| `city_id` | | UUID | From `master_city` table — use `/v1/master/cities` to get city list |
| `metadata` | | object | Any extra key-value data |

**Response (201):**
```json
{
  "message": "Branch created successfully.",
  "branch": {
    "branch_id":     "new-uuid",
    "name":          "Mumbai HO",
    "branch_code":   "MUM-HO",
    "branch_type":   "branch",
    "company_id":    "815fcdb9-...",
    "address":       "123 Link Road, Andheri, Mumbai",
    "mobile_number": "9876543210",
    "owner_name":    "Rajesh Gupta",
    "city_id":       "f416e290-...",
    "metadata":      {},
    "created_at":    "2026-05-05T10:00:00Z",
    "updated_at":    "2026-05-05T10:00:00Z"
  }
}
```

---

## Update Branch

```
PATCH /v1/staff/branches/{branch_id}
```

Only send fields you want to change — omitted fields are untouched.

```json
{
  "mobile_number": "9988776655",
  "owner_name":    "Suresh Gupta",
  "city_id":       "f416e290-b5c1-47d3-a4e3-fe174a99540f"
}
```

Other examples:

```json
{ "name": "Mumbai Head Office" }

{ "address": "456 New Link Road, Andheri West" }

{ "branch_type": "hub" }
```

**Response (200):**
```json
{
  "message": "Branch updated successfully.",
  "branch": { ...updated branch object... }
}
```

---

## List Branches

```
GET /v1/staff/branches
```

**Response:**
```json
{
  "company_id": "815fcdb9-...",
  "count": 3,
  "branches": [
    {
      "branch_id":     "0c15b4c4-...",
      "name":          "NLP Head Office",
      "branch_code":   "NLP-HO",
      "branch_type":   "primary",
      "address":       null,
      "mobile_number": "9876543210",
      "owner_name":    "Rajesh Gupta",
      "city_id":       "f416e290-...",
      "metadata":      {},
      "created_at":    "2026-04-27T02:30:00Z",
      "updated_at":    "2026-05-05T10:00:00Z"
    }
  ]
}
```

---

## Get City List (for `city_id`)

```
GET /v1/master/cities?is_active=true
```

Use the `city_id` from this response when creating or updating a branch.
