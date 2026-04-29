# Master Data API

All endpoints are under `/v1/master` and require a valid JWT (`Authorization: Bearer <token>`).
Every operation is **company-scoped** — data from other companies is never accessible.

---

## Endpoints Overview

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/master/branches` | Create a branch in your company |
| `GET` | `/v1/master/branches` | List all branches in your company |
| `GET` | `/v1/master/branches/{branch_id}` | Get a branch |
| `PATCH` | `/v1/master/branches/{branch_id}` | Update a branch |
| `POST` | `/v1/master/states` | Create a state |
| `POST` | `/v1/master/states/bulk` | Bulk create states |
| `GET` | `/v1/master/states` | List states |
| `GET` | `/v1/master/states/{state_id}` | Get a state |
| `PATCH` | `/v1/master/states/{state_id}` | Update a state |
| `PATCH` | `/v1/master/states/bulk` | Bulk update states |
| `POST` | `/v1/master/cities` | Create a city |
| `POST` | `/v1/master/cities/bulk` | Bulk create cities |
| `GET` | `/v1/master/cities` | List cities |
| `GET` | `/v1/master/cities/{city_id}` | Get a city |
| `PATCH` | `/v1/master/cities/{city_id}` | Update a city |
| `PATCH` | `/v1/master/cities/bulk` | Bulk update cities |
| `POST` | `/v1/master/transports` | Create a transport |
| `POST` | `/v1/master/transports/bulk` | Bulk create transports |
| `GET` | `/v1/master/transports` | List transports |
| `GET` | `/v1/master/transports/{transport_id}` | Get a transport |
| `PATCH` | `/v1/master/transports/{transport_id}` | Update a transport |
| `PATCH` | `/v1/master/transports/bulk` | Bulk update transports |
| `POST` | `/v1/master/city-transports` | Link transport to a city |
| `POST` | `/v1/master/city-transports/bulk` | Bulk link transports to cities |
| `GET` | `/v1/master/city-transports` | List city-transport links |
| `GET` | `/v1/master/city-transports/{id}` | Get a city-transport link |
| `PATCH` | `/v1/master/city-transports/{id}` | Update a city-transport link |
| `PATCH` | `/v1/master/city-transports/bulk` | Bulk update city-transport links |

---

## Authentication

Every request needs the token from `POST /v1/auth/login`:

```http
Authorization: Bearer <access_token>
```

---

## 3. Branches

Branches belong to the company the caller is logged in to. All branch operations are automatically scoped to that company via the JWT — you can never see or modify another company's branches.

### `POST /v1/master/branches` — Create a branch

```json
{
  "name":        "Pune Office",
  "branch_code": "PUN001",
  "branch_type": "branch",
  "address":     "FC Road, Pune 411004",
  "metadata":    {}
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | Yes | Display name |
| `branch_code` | string | Yes | Must be unique within your company |
| `branch_type` | string | No | `primary` \| `hub` \| `branch` (default: `branch`) |
| `address` | string | No | — |
| `metadata` | object | No | Any extra key-value data |

**201 Created**
```json
{
  "message": "Branch created.",
  "branch": {
    "branch_id":   "a1b2c3d4-...",
    "name":        "Pune Office",
    "branch_code": "PUN001",
    "branch_type": "branch",
    "company_id":  "534b7a1a-...",
    "address":     "FC Road, Pune 411004",
    "metadata":    {},
    "created_at":  "2026-04-26T10:00:00Z",
    "updated_at":  "2026-04-26T10:00:00Z"
  }
}
```

| Error | When |
|-------|------|
| `409 Conflict` | `branch_code` already exists in your company |
| `401 Unauthorized` | Missing/invalid token |

---

### `GET /v1/master/branches` — List branches

Returns all branches belonging to the caller's company, ordered by name.

**200 OK**
```json
{
  "count": 2,
  "branches": [
    {
      "branch_id":   "758297fc-...",
      "name":        "Main Office",
      "branch_code": "TM001",
      "branch_type": "primary",
      "address":     null,
      "created_at":  "2026-04-25T00:23:05Z"
    },
    {
      "branch_id":   "a1b2c3d4-...",
      "name":        "Pune Office",
      "branch_code": "PUN001",
      "branch_type": "branch",
      "address":     "FC Road, Pune 411004",
      "created_at":  "2026-04-26T10:00:00Z"
    }
  ]
}
```

---

### `GET /v1/master/branches/{branch_id}` — Get a branch

Returns a single branch. Returns `404` if the branch doesn't belong to your company.

---

### `PATCH /v1/master/branches/{branch_id}` — Update a branch

Send only the fields you want to change:

```json
{ "address": "New Address, Pune 411001" }
```

```json
{ "branch_type": "hub", "name": "Pune Hub" }
```

**200 OK**
```json
{
  "message": "Branch updated.",
  "branch": { ... }
}
```

---

## 2. States

### `POST /v1/master/states` — Create a state

```json
{
  "state_name": "Maharashtra",
  "state_code": "MH",
  "branch_id": "758297fc-c95a-4d15-b869-004c367e45e4",
  "is_active": true
}
```

**201 Created**
```json
{
  "message": "State created.",
  "state": {
    "state_id": "aaa00001-...",
    "state_name": "Maharashtra",
    "state_code": "MH",
    "company_id": "...",
    "branch_id": "758297fc-...",
    "total_city_count": 0,
    "is_active": true,
    "created_at": "2026-04-26T10:00:00Z"
  }
}
```

| Error | When |
|-------|------|
| `409 Conflict` | `state_code` already exists in this branch |
| `401 Unauthorized` | Missing/invalid token |

---

### `POST /v1/master/states/bulk` — Bulk create states

```json
{
  "branch_id": "758297fc-c95a-4d15-b869-004c367e45e4",
  "items": [
    { "state_name": "Gujarat",     "state_code": "GJ", "branch_id": "758297fc-..." },
    { "state_name": "Rajasthan",   "state_code": "RJ", "branch_id": "758297fc-..." },
    { "state_name": "Maharashtra", "state_code": "MH", "branch_id": "758297fc-..." }
  ]
}
```

> `branch_id` at the top level is the default; individual items can override it.

**201 Created**
```json
{
  "created_count": 2,
  "error_count": 1,
  "created": [ { "state_id": "...", "state_name": "Gujarat", ... }, ... ],
  "errors": [
    { "index": 2, "state_code": "MH", "error": "Duplicate state_code in this branch." }
  ]
}
```

A partial success (some created, some failed) still returns `201`. Check `error_count`.

---

### `GET /v1/master/states` — List states

| Query param | Type | Description |
|-------------|------|-------------|
| `branch_id` | UUID | Filter by branch |
| `is_active` | bool | `true` / `false` |

**200 OK**
```json
{
  "count": 2,
  "states": [
    { "state_id": "...", "state_name": "Gujarat", "state_code": "GJ", "total_city_count": 5, ... },
    { "state_id": "...", "state_name": "Maharashtra", "state_code": "MH", "total_city_count": 12, ... }
  ]
}
```

---

### `GET /v1/master/states/{state_id}` — Get a state

Returns full row including `total_city_count` (auto-maintained by DB trigger).

---

### `PATCH /v1/master/states/{state_id}` — Update a state

Send only the fields you want to change:

```json
{ "is_active": false }
```

---

### `PATCH /v1/master/states/bulk` — Bulk update states

```json
{
  "items": [
    { "state_id": "aaa00001-...", "is_active": false },
    { "state_id": "aaa00002-...", "state_name": "Goa (Updated)" }
  ]
}
```

**200 OK**
```json
{
  "updated_count": 2,
  "error_count": 0,
  "updated": [ ... ],
  "errors": []
}
```

---

## 4. Cities

> `total_city_count` on the parent state is updated **automatically** by the DB when cities are added or removed.

### `POST /v1/master/cities` — Create a city

```json
{
  "city_name":     "Mumbai",
  "city_code":     "MUM",
  "city_pin_code": "400001",
  "state_id":      "aaa00001-...",
  "branch_id":     "758297fc-...",
  "is_active":     true
}
```

| Error | When |
|-------|------|
| `409 Conflict` | `city_code` already exists in this branch |
| `404 Not Found` | `state_id` doesn't belong to your company |

---

### `POST /v1/master/cities/bulk` — Bulk create cities

```json
{
  "branch_id": "758297fc-...",
  "items": [
    { "city_name": "Mumbai",  "city_code": "MUM", "city_pin_code": "400001", "state_id": "aaa00001-...", "branch_id": "758297fc-..." },
    { "city_name": "Pune",    "city_code": "PUN", "city_pin_code": "411001", "state_id": "aaa00001-...", "branch_id": "758297fc-..." },
    { "city_name": "Nashik",  "city_code": "NSK", "city_pin_code": "422001", "state_id": "aaa00001-...", "branch_id": "758297fc-..." }
  ]
}
```

---

### `GET /v1/master/cities` — List cities

| Query param | Type | Description |
|-------------|------|-------------|
| `branch_id` | UUID | Filter by branch |
| `state_id`  | UUID | Filter by state |
| `is_active` | bool | `true` / `false` |

---

### `PATCH /v1/master/cities/bulk` — Bulk update cities

```json
{
  "items": [
    { "city_id": "bbb00001-...", "city_pin_code": "400002" },
    { "city_id": "bbb00002-...", "is_active": false }
  ]
}
```

---

## 5. Transports

### `POST /v1/master/transports` — Create a transport

```json
{
  "transport_code": "VRL001",
  "transport_name": "VRL Logistics",
  "branch_id":      "758297fc-...",
  "gstin":          "29ABCDE1234F1Z5",
  "mobile_number_owner": [
    { "name": "Ramesh (Owner)", "mobile": "9876543210" }
  ],
  "website": "https://vrlgroup.in",
  "address": "VRL Complex, Hubli",
  "metadata": {},
  "is_active": true
}
```

| Field | Type | Notes |
|-------|------|-------|
| `transport_code` | string | Unique per company+branch |
| `mobile_number_owner` | array | `[{"name":"...","mobile":"..."}]` — multiple owners allowed |
| `metadata` | object | Any extra key-value data |

---

### `POST /v1/master/transports/bulk` — Bulk create transports

```json
{
  "branch_id": "758297fc-...",
  "items": [
    { "transport_code": "VRL001", "transport_name": "VRL Logistics", "branch_id": "758297fc-...", ... },
    { "transport_code": "SFC001", "transport_name": "SFC Express",   "branch_id": "758297fc-...", ... }
  ]
}
```

---

### `GET /v1/master/transports` — List transports

| Query param | Type | Description |
|-------------|------|-------------|
| `branch_id` | UUID | Filter by branch |
| `is_active` | bool | `true` / `false` |

---

### `PATCH /v1/master/transports/{transport_id}` — Update a transport

```json
{
  "mobile_number_owner": [
    { "name": "Ramesh (Owner)", "mobile": "9876543210" },
    { "name": "Suresh (Manager)", "mobile": "9123456789" }
  ],
  "is_active": true
}
```

---

### `PATCH /v1/master/transports/bulk` — Bulk update transports

```json
{
  "items": [
    { "transport_id": "ccc00001-...", "is_active": false },
    { "transport_id": "ccc00002-...", "gstin": "29XXXXX9999X1Z5" }
  ]
}
```

---

## 6. City-wise Transport

Links a transport vendor to a specific city within a branch. Useful for knowing which transport operates in which city, with branch-specific contact numbers and a manager name.

### `POST /v1/master/city-transports` — Link a transport to a city

```json
{
  "city_id":      "bbb00001-...",
  "transport_id": "ccc00001-...",
  "branch_id":    "758297fc-...",
  "branch_mobile": [
    { "label": "booking",   "mobile": "9000000001" },
    { "label": "complaint", "mobile": "9000000002" }
  ],
  "address":      "VRL Depot, Mumbai",
  "manager_name": "Ajay Patil",
  "is_active":    true
}
```

| Error | When |
|-------|------|
| `409 Conflict` | Same city+transport already linked in this branch |
| `404 Not Found` | `city_id` or `transport_id` not in your company |

---

### `POST /v1/master/city-transports/bulk` — Bulk link transports to cities

```json
{
  "branch_id": "758297fc-...",
  "items": [
    { "city_id": "bbb00001-...", "transport_id": "ccc00001-...", "branch_id": "758297fc-...", "branch_mobile": [...], "manager_name": "Ajay" },
    { "city_id": "bbb00002-...", "transport_id": "ccc00001-...", "branch_id": "758297fc-...", "branch_mobile": [...], "manager_name": "Priya" }
  ]
}
```

---

### `GET /v1/master/city-transports` — List city-transport links

| Query param | Type | Description |
|-------------|------|-------------|
| `branch_id`    | UUID | Filter by branch |
| `city_id`      | UUID | Filter by city |
| `transport_id` | UUID | Filter by transport |
| `is_active`    | bool | `true` / `false` |

---

### `PATCH /v1/master/city-transports/{id}` — Update a link

```json
{
  "manager_name": "Suresh Kumar",
  "branch_mobile": [
    { "label": "booking", "mobile": "9111111111" }
  ]
}
```

---

### `PATCH /v1/master/city-transports/bulk` — Bulk update links

```json
{
  "items": [
    { "id": "ddd00001-...", "is_active": false },
    { "id": "ddd00002-...", "manager_name": "New Manager" }
  ]
}
```

---

## Bulk Operation Response Format

All bulk endpoints return a consistent shape:

```json
{
  "created_count": 3,
  "error_count":   1,
  "created": [ { ... }, { ... }, { ... } ],
  "errors": [
    { "index": 2, "error": "Duplicate state_code in this branch." }
  ]
}
```

For bulk **update**:
```json
{
  "updated_count": 2,
  "error_count":   1,
  "updated": [ { ... }, { ... } ],
  "errors": [
    { "index": 1, "state_id": "...", "error": "Not found or no change." }
  ]
}
```

- `index` is the 0-based position in the request `items` array.
- Partial success is normal — process `errors` to retry only failed items.

---

## Quick Test (PowerShell)

```powershell
# Login
$body = '{"email":"alice@techmove.io","password":"Alice@9876"}'
$r    = Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/auth/login" `
          -Method POST -ContentType "application/json" -Body $body -UseBasicParsing | ConvertFrom-Json
$TOKEN     = $r.access_token
$BRANCH_ID = $r.user.branch_id

# Create a new branch
$branchBody = ConvertTo-Json @{name="Pune Office"; branch_code="PUN001"; branch_type="branch"; address="FC Road, Pune"}
$branch = Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/master/branches" `
  -Method POST -ContentType "application/json" `
  -Headers @{Authorization="Bearer $TOKEN"} -Body $branchBody -UseBasicParsing | ConvertFrom-Json
$NEW_BRANCH_ID = $branch.branch.branch_id

# List all branches
(Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/master/branches" `
  -Headers @{Authorization="Bearer $TOKEN"} -UseBasicParsing).Content | ConvertFrom-Json | Select-Object -ExpandProperty branches | Format-Table branch_id, name, branch_code, branch_type -AutoSize

# Create a state
$state = Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/master/states" `
  -Method POST -ContentType "application/json" `
  -Headers @{Authorization="Bearer $TOKEN"} `
  -Body (ConvertTo-Json @{state_name="Maharashtra";state_code="MH";branch_id=$BRANCH_ID}) `
  -UseBasicParsing | ConvertFrom-Json
$STATE_ID = $state.state.state_id

# Create a city
$city = Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/master/cities" `
  -Method POST -ContentType "application/json" `
  -Headers @{Authorization="Bearer $TOKEN"} `
  -Body (ConvertTo-Json @{city_name="Mumbai";city_code="MUM";city_pin_code="400001";state_id=$STATE_ID;branch_id=$BRANCH_ID}) `
  -UseBasicParsing | ConvertFrom-Json
$CITY_ID = $city.city.city_id

# Create a transport
$transport = Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/master/transports" `
  -Method POST -ContentType "application/json" `
  -Headers @{Authorization="Bearer $TOKEN"} `
  -Body (ConvertTo-Json @{transport_code="VRL001";transport_name="VRL Logistics";branch_id=$BRANCH_ID;mobile_number_owner=@(@{name="Owner";mobile="9876543210"})}) `
  -UseBasicParsing | ConvertFrom-Json
$TRANSPORT_ID = $transport.transport.transport_id

# Link transport to city
Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/master/city-transports" `
  -Method POST -ContentType "application/json" `
  -Headers @{Authorization="Bearer $TOKEN"} `
  -Body (ConvertTo-Json @{city_id=$CITY_ID;transport_id=$TRANSPORT_ID;branch_id=$BRANCH_ID;manager_name="Ajay Patil";branch_mobile=@(@{label="booking";mobile="9000000001"})}) `
  -UseBasicParsing

# Bulk create cities
$bulkBody = ConvertTo-Json -Depth 4 @{
  branch_id = $BRANCH_ID
  items = @(
    @{city_name="Pune";  city_code="PUN"; city_pin_code="411001"; state_id=$STATE_ID; branch_id=$BRANCH_ID},
    @{city_name="Nashik";city_code="NSK"; city_pin_code="422001"; state_id=$STATE_ID; branch_id=$BRANCH_ID}
  )
}
Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/master/cities/bulk" `
  -Method POST -ContentType "application/json" `
  -Headers @{Authorization="Bearer $TOKEN"} -Body $bulkBody -UseBasicParsing
```
