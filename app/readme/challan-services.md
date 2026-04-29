# Challan Services — API Reference

All endpoints require a valid JWT in the `Authorization: Bearer <token>` header.  
Company, branch, and user identity are resolved automatically from the token — never pass them in the request body.

**Base path:** `/v1/challan`

---

## Table of Contents

1. [Overview & Concepts](#0-overview--concepts)
2. [Challan Template](#1-challan-template)
3. [Challan Book](#2-challan-book)
4. [Challan Trip Sheet](#3-challan-trip-sheet)
5. [Challan](#4-challan)
6. [Data Flow](#5-data-flow)
7. [Status Machines](#6-status-machines)
8. [Primary Challan Feature](#7-primary-challan-feature)
9. [Error Reference](#8-error-reference)

---

## 0. Overview & Concepts

The challan module handles the dispatch side of goods transport. Here is how the objects relate:

```
Company
 └── Branch
      ├── ChallanTemplate   — print layout definitions
      ├── ChallanBook       — numbered series for challan nos
      ├── Challan           — one dispatch note (groups bilties going on one truck)
      │    └── Bilty[]      — individual consignment notes
      └── (company-wide)
           └── ChallanTripSheet — groups challans from multiple branches on one truck journey
                └── Challan[]
```

**Key rules:**
- A **Challan** is branch-scoped. Each branch manages its own challans independently.
- A **Trip Sheet** is company-scoped. It can contain challans from different branches.
- Each branch can have exactly **one primary challan** (open, not yet dispatched) at a time.
- Each branch can have exactly **one primary book** per active book series at a time.
- When a challan is **dispatched**, all its bilties are dispatched simultaneously and `is_primary` is auto-cleared.

---

## 1. Challan Template

Templates define **how a challan is printed**. They are branch-scoped. Each branch can set one default per `template_type`.

### Template Types

| Value | Description |
|---|---|
| `CHALLAN` | Standard dispatch challan |
| `SUMMARY` | Summary sheet for a trip |
| `KAAT_RECEIPT` | Kaat / unloading receipt |
| `LOADING_CHALLAN` | Loading / loading slip |

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/challan/template` | Create a template |
| `GET` | `/v1/challan/template` | List templates |
| `GET` | `/v1/challan/template/primary` | Get default template for a type |
| `GET` | `/v1/challan/template/{template_id}` | Get template by ID |
| `PUT` | `/v1/challan/template/{template_id}` | Update template |
| `DELETE` | `/v1/challan/template/{template_id}` | Soft-delete template |
| `POST` | `/v1/challan/template/{template_id}/set-primary` | Set as default for its type |

---

### `POST /v1/challan/template` — Create Template

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | string | ✅ | Short unique code, max 50 chars. e.g. `"CHLN-A4"` |
| `name` | string | ✅ | Display name, max 150 chars |
| `slug` | string | ✅ | URL-safe identifier, max 100 chars |
| `template_type` | string | ✅ | One of `CHALLAN`, `SUMMARY`, `KAAT_RECEIPT`, `LOADING_CHALLAN` |
| `description` | string | ❌ | Human-readable description |
| `config` | object | ❌ | JSON config for the print renderer (paper size, logo, columns, etc.) |
| `is_default` | boolean | ❌ | `false`. Use `/set-primary` to promote after creation |
| `is_active` | boolean | ❌ | Default `true` |

```json
{
  "code": "CHLN-A4",
  "name": "Standard Challan A4",
  "slug": "standard-challan-a4",
  "template_type": "CHALLAN",
  "description": "Default A4 portrait challan with company header",
  "config": {
    "paper_size": "A4",
    "orientation": "portrait",
    "show_logo": true,
    "show_gstin": true,
    "columns": ["gr_no", "consignor", "consignee", "pkgs", "weight", "freight"]
  }
}
```

**Response:** Created template object.

---

### `GET /v1/challan/template` — List Templates

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `template_type` | string | — | Filter by type |
| `is_active` | boolean | `true` | `false` to list soft-deleted ones |

---

### `GET /v1/challan/template/primary` — Get Default Template

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `template_type` | string | `CHALLAN` | Which type to query |

Returns `404` if no default is set for that type in the branch.

---

### `PUT /v1/challan/template/{template_id}` — Update Template

**Request body (all optional):**

| Field | Type | Description |
|---|---|---|
| `name` | string | New display name |
| `description` | string | New description |
| `config` | object | Replace entire config object |
| `is_default` | boolean | — |
| `is_active` | boolean | Set `false` to soft-delete |

---

### `POST /v1/challan/template/{template_id}/set-primary`

Sets this template as the default for its `template_type` in the branch.  
Automatically unsets the previous default for that type.  
No request body needed.

---

## 2. Challan Book

Books hold the **numbered sequence** for challan numbers. A `current_number` pointer advances atomically each time a number is claimed.

### Route Scopes

| Value | Description |
|---|---|
| `OPEN` | Book can be used for any destination |
| `FIXED_ROUTE` | Book is tied to a specific `from_branch → to_branch` leg. **Both `from_branch_id` and `to_branch_id` are required.** |

### Number Format

Generated challan number = `prefix` + zero-padded(`current_number`, `digits`) + `postfix`

**Example:** prefix=`"MUM/"`, digits=`4`, postfix=`"/25"`, current_number=`42` → `"MUM/0042/25"`

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/challan/book` | Create a challan book |
| `GET` | `/v1/challan/book` | List books (many filters) |
| `GET` | `/v1/challan/book/primary` | Get primary book for current branch |
| `GET` | `/v1/challan/book/next-no` | Claim next number from primary book |
| `GET` | `/v1/challan/book/by-route` | Find active FIXED_ROUTE book for a leg |
| `GET` | `/v1/challan/book/{book_id}` | Get book by ID |
| `GET` | `/v1/challan/book/{book_id}/next-no` | Claim next number from specific book |
| `PUT` | `/v1/challan/book/{book_id}` | Update book |
| `DELETE` | `/v1/challan/book/{book_id}` | Soft-delete book |
| `POST` | `/v1/challan/book/{book_id}/set-primary` | Set as primary for current branch |

---

### `POST /v1/challan/book` — Create Book

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `book_name` | string | ❌ | Human label, e.g. `"FY25-26 Batch A"` |
| `template_id` | UUID | ❌ | Default print template for challans from this book |
| `route_scope` | string | ❌ | `"OPEN"` (default) or `"FIXED_ROUTE"` |
| `from_branch_id` | UUID | ✅ if FIXED_ROUTE | Origin branch UUID |
| `to_branch_id` | UUID | ✅ if FIXED_ROUTE | Destination branch UUID |
| `prefix` | string | ❌ | Text prepended to number, e.g. `"MUM/"` |
| `from_number` | integer | ✅ | First number (inclusive, > 0) |
| `to_number` | integer | ✅ | Last number (inclusive, ≥ from_number) |
| `digits` | integer | ❌ | Zero-pad width (1–10, default `4`) |
| `postfix` | string | ❌ | Text appended after number, e.g. `"/25"` |
| `is_fixed` | boolean | ❌ | `true` = number never advances (same no. every time) |
| `auto_continue` | boolean | ❌ | `true` = auto-create next book when exhausted |
| `is_primary` | boolean | ❌ | Promote to primary immediately on creation |
| `metadata` | object | ❌ | Arbitrary key-value store |

**OPEN book example:**
```json
{
  "book_name": "Main Challan Book FY25-26",
  "route_scope": "OPEN",
  "prefix": "MUM/",
  "from_number": 1,
  "to_number": 9999,
  "digits": 4,
  "is_primary": true,
  "auto_continue": true,
  "metadata": { "financial_year": "2025-26" }
}
```

**FIXED_ROUTE book example:**
```json
{
  "book_name": "Mumbai → Delhi Route Book",
  "route_scope": "FIXED_ROUTE",
  "from_branch_id": "uuid-of-mumbai-branch",
  "to_branch_id": "uuid-of-delhi-branch",
  "prefix": "MD/",
  "from_number": 1,
  "to_number": 500,
  "digits": 3,
  "is_primary": true
}
```

**Validation errors (422):**
- `route_scope=FIXED_ROUTE` but `from_branch_id` or `to_branch_id` is missing
- `from_number > to_number`

---

### `GET /v1/challan/book` — List Books

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `route_scope` | string | — | `OPEN` or `FIXED_ROUTE` |
| `from_branch_id` | UUID | — | Filter FIXED_ROUTE books by origin |
| `to_branch_id` | UUID | — | Filter FIXED_ROUTE books by destination |
| `is_active` | boolean | `true` | `false` to include soft-deleted |
| `is_completed` | boolean | — | `true` = exhausted; `false` = has remaining numbers |
| `is_primary` | boolean | — | `true` = only the primary book |

---

### `GET /v1/challan/book/by-route` — Find Book for a Specific Leg

Returns the active, non-exhausted `FIXED_ROUTE` book for a given origin → destination.  
If multiple books match, the **primary** book is returned first.

**Query params:**

| Param | Type | Required | Description |
|---|---|---|---|
| `from_branch_id` | UUID | ✅ | Origin branch UUID |
| `to_branch_id` | UUID | ✅ | Destination branch UUID |

```
GET /v1/challan/book/by-route?from_branch_id=<uuid>&to_branch_id=<uuid>
```

Returns `404` if no active FIXED_ROUTE book exists for that leg.

**Typical frontend usage:** When a user selects a FIXED_ROUTE challan scope, call this to auto-populate the book and pre-generate the next challan number.

---

### `GET /v1/challan/book/next-no` — Claim Next Number (Primary Book)

Atomically claims and returns the next available challan number from the branch primary book. The `current_number` is incremented in the database.

> ⚠️ This is a **write operation** — every call advances the counter.

**Response:**
```json
{
  "challan_no": "MUM/0042",
  "challan_number": 42
}
```

Returns `404` if no primary book exists, `410` if the book is exhausted.

---

### `GET /v1/challan/book/{book_id}/next-no` — Claim from Specific Book

Same as above but targets a specific book by ID.

---

### `PUT /v1/challan/book/{book_id}` — Update Book

**Request body (all optional):**

| Field | Type | Description |
|---|---|---|
| `book_name` | string | New label |
| `template_id` | UUID | Change linked template |
| `from_branch_id` | UUID | Correct origin branch |
| `to_branch_id` | UUID | Correct destination branch |
| `is_fixed` | boolean | Toggle fixed-number mode |
| `auto_continue` | boolean | Toggle auto-continue |
| `is_active` | boolean | `false` to soft-delete |
| `is_primary` | boolean | Promote (prefer `/set-primary` endpoint) |
| `metadata` | object | Replace metadata |

---

### `POST /v1/challan/book/{book_id}/set-primary`

Promotes this book to primary for the current branch.  
Automatically demotes the existing primary (if any).  
No request body needed.

---

## 3. Challan Trip Sheet

A trip sheet represents **one truck journey** and is **company-scoped** — it can contain challans from multiple branches. It is the outermost grouping object.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/challan/trip-sheet` | Create a trip sheet |
| `GET` | `/v1/challan/trip-sheet` | List trip sheets |
| `GET` | `/v1/challan/trip-sheet/{trip_sheet_id}` | Get trip sheet + all its challans |
| `PUT` | `/v1/challan/trip-sheet/{trip_sheet_id}` | Update trip sheet details |
| `POST` | `/v1/challan/trip-sheet/{trip_sheet_id}/dispatch` | Mark as dispatched |
| `POST` | `/v1/challan/trip-sheet/{trip_sheet_id}/arrive` | Mark as arrived |

---

### `POST /v1/challan/trip-sheet` — Create Trip Sheet

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `trip_sheet_no` | string | ✅ | Unique trip sheet number, max 50 chars |
| `transport_id` | UUID | ❌ | Master transport record UUID |
| `transport_name` | string | ❌ | Transport/lorry contractor name |
| `transport_gstin` | string | ❌ | GSTIN of transporter (max 15 chars) |
| `from_city_id` | UUID | ❌ | Origin city UUID |
| `to_city_id` | UUID | ❌ | Destination city UUID |
| `vehicle_info` | object | ❌ | Free-form vehicle details (see example) |
| `trip_date` | string | ❌ | ISO date `YYYY-MM-DD` |
| `remarks` | string | ❌ | Free-text remarks |
| `metadata` | object | ❌ | Arbitrary key-value store |

```json
{
  "trip_sheet_no": "TS-2025-001",
  "transport_name": "Sharma Transport Co.",
  "transport_gstin": "27AABCS1429B1ZB",
  "from_city_id": "uuid-mumbai",
  "to_city_id": "uuid-delhi",
  "vehicle_info": {
    "vehicle_no": "MH04AB1234",
    "vehicle_type": "22ft Trailer",
    "driver_name": "Ramesh Kumar",
    "driver_mobile": "9876543210",
    "lr_no": "LR123456"
  },
  "trip_date": "2025-04-28",
  "remarks": "Fragile goods — handle with care"
}
```

---

### `GET /v1/challan/trip-sheet` — List Trip Sheets

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `trip_status` | string | — | `DRAFT`, `OPEN`, `DISPATCHED`, `ARRIVED`, `CLOSED` |
| `from_date` | string | — | ISO date, inclusive lower bound on `trip_date` |
| `to_date` | string | — | ISO date, inclusive upper bound on `trip_date` |
| `is_active` | boolean | `true` | |
| `limit` | integer | `50` | Max 200 |
| `offset` | integer | `0` | For pagination |

---

### `GET /v1/challan/trip-sheet/{trip_sheet_id}` — Get Trip Sheet

Returns the trip sheet object **with a `challans` array** embedded:

```json
{
  "trip_sheet_id": "...",
  "trip_sheet_no": "TS-2025-001",
  "status": "OPEN",
  "total_challan_count": 2,
  "total_bilty_count": 15,
  "total_freight": 45000.00,
  "total_weight": 3200.5,
  "total_packages": 48,
  "challans": [
    { "challan_id": "...", "challan_no": "MUM/0042", "branch_id": "...", ... },
    { "challan_id": "...", "challan_no": "MUM/0043", "branch_id": "...", ... }
  ]
}
```

---

### `POST /v1/challan/trip-sheet/{trip_sheet_id}/dispatch`

Marks the trip sheet as `DISPATCHED`. No request body needed.

**Allowed from:** `DRAFT` or `OPEN` status.  
**Blocked if:** already `DISPATCHED`, `ARRIVED`, or `CLOSED` → `409`.

---

### `POST /v1/challan/trip-sheet/{trip_sheet_id}/arrive`

Marks the trip sheet as `ARRIVED`. No request body needed.

**Allowed from:** `DISPATCHED` status only → `409` otherwise.

---

## 4. Challan

A challan is a **branch-level dispatch note**. It groups all bilties going on the same truck from a branch on a given day.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/challan` | Create challan |
| `GET` | `/v1/challan` | List challans |
| `GET` | `/v1/challan/primary` | Get primary (active open) challan for branch |
| `GET` | `/v1/challan/available-bilties` | Bilties not yet in any challan |
| `GET` | `/v1/challan/{challan_id}` | Get challan + embedded bilties |
| `PUT` | `/v1/challan/{challan_id}` | Update challan details |
| `POST` | `/v1/challan/{challan_id}/set-primary` | Set as primary for branch |
| `POST` | `/v1/challan/{challan_id}/dispatch` | Dispatch challan + all bilties |
| `POST` | `/v1/challan/{challan_id}/arrive-hub` | Mark arrived at hub + all bilties |
| `GET` | `/v1/challan/{challan_id}/bilties` | List bilties on this challan |
| `POST` | `/v1/challan/{challan_id}/add-bilty` | Add a bilty |
| `POST` | `/v1/challan/{challan_id}/remove-bilty/{bilty_id}` | Remove a bilty |
| `POST` | `/v1/challan/{challan_id}/move-to-trip-sheet` | Assign to a trip sheet |
| `POST` | `/v1/challan/{challan_id}/remove-from-trip-sheet` | Detach from trip sheet |

---

### `POST /v1/challan` — Create Challan

> **Auto-number:** Omit `challan_no` to have the backend atomically claim the next number from the branch primary book (or from `book_id` if provided).

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `challan_no` | string | ❌ | Omit to auto-claim from primary/specified book |
| `book_id` | UUID | ❌ | Specific book to claim number from (overrides primary) |
| `template_id` | UUID | ❌ | Print template for this challan |
| `trip_sheet_id` | UUID | ❌ | Assign to a trip sheet immediately |
| `from_branch_id` | UUID | ❌ | Origin branch (defaults to current branch) |
| `to_branch_id` | UUID | ❌ | Destination branch |
| `transport_id` | UUID | ❌ | Master transport record UUID |
| `transport_name` | string | ❌ | Transport / lorry contractor name |
| `transport_gstin` | string | ❌ | Transporter GSTIN (max 15 chars) |
| `vehicle_info` | object | ❌ | Free-form vehicle details |
| `challan_date` | string | ❌ | ISO date `YYYY-MM-DD` (defaults to today) |
| `remarks` | string | ❌ | Free-text remarks |
| `is_primary` | boolean | ❌ | Set `true` to make this the branch primary immediately |
| `metadata` | object | ❌ | Arbitrary key-value store |

**Minimal example (auto-number from primary book, set as primary):**
```json
{
  "to_branch_id": "uuid-delhi-branch",
  "transport_name": "Sharma Transport",
  "vehicle_info": { "vehicle_no": "MH04AB1234", "driver_name": "Ramesh" },
  "challan_date": "2025-04-28",
  "is_primary": true
}
```

**Full example:**
```json
{
  "book_id": "uuid-fixed-route-book",
  "template_id": "uuid-challan-template",
  "trip_sheet_id": "uuid-trip-sheet",
  "from_branch_id": "uuid-mumbai-branch",
  "to_branch_id": "uuid-delhi-branch",
  "transport_id": "uuid-transport",
  "transport_name": "Sharma Transport Co.",
  "transport_gstin": "27AABCS1429B1ZB",
  "vehicle_info": {
    "vehicle_no": "MH04AB1234",
    "vehicle_type": "22ft Trailer",
    "driver_name": "Ramesh Kumar",
    "driver_mobile": "9876543210"
  },
  "challan_date": "2025-04-28",
  "remarks": "Night departure",
  "is_primary": true,
  "metadata": { "seal_no": "SL-5520" }
}
```

**Response:** Created challan object including the auto-assigned `challan_no`.

---

### `GET /v1/challan` — List Challans

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `challan_status` | string | — | `DRAFT`, `OPEN`, `DISPATCHED`, `ARRIVED_HUB`, `CLOSED` |
| `from_date` | string | — | ISO date lower bound on `challan_date` |
| `to_date` | string | — | ISO date upper bound on `challan_date` |
| `trip_sheet_id` | UUID | — | List all challans on a specific trip sheet |
| `is_active` | boolean | `true` | |
| `limit` | integer | `50` | Max 200 |
| `offset` | integer | `0` | Pagination |

---

### `GET /v1/challan/primary` — Get Primary Challan

Returns the current primary open challan for the authenticated branch.  
Returns `404` if none is set.

**Frontend use case:** Call this at the start of the billing workflow to know which challan new bilties will be auto-assigned to.

---

### `GET /v1/challan/available-bilties` — List Unassigned Bilties

Returns bilties that have **not been assigned to any challan** (`challan_id IS NULL`) and are in status `SAVED` or `DRAFT`.

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `to_city_id` | UUID | — | Filter by destination city |
| `from_date` | string | — | ISO date lower bound on bilty date |
| `to_date` | string | — | ISO date upper bound on bilty date |
| `limit` | integer | `100` | Max 500 |
| `offset` | integer | `0` | Pagination |

**Frontend use case:** Load this list on the "Add bilties to challan" screen so the user can pick which consignments go on today's truck.

**Each result object contains:**

| Field | Description |
|-------|-------------|
| `bilty_id` | UUID |
| `gr_no` | GR / LR number |
| `bilty_date` | Date of bilty |
| `bilty_type` | `REGULAR` or `MANUAL` |
| `consignor_name` / `consignor_mobile` | Sender snapshot |
| `consignee_name` / `consignee_mobile` | Receiver snapshot |
| `from_city_id` / `to_city_id` | Origin / destination city UUIDs |
| `delivery_type` | `DOOR` or `GODOWN` |
| `payment_mode` | `PAID`, `TO-PAY`, or `FOC` |
| `contain` | Description of goods |
| `pvt_marks` | Private marks on packages |
| `no_of_pkg` | Number of packages |
| `weight` / `actual_weight` | Billed / physical weight |
| `total_amount` | Total freight |
| `invoice_no` / `invoice_value` | Commercial invoice details |
| `status` | `SAVED` or `DRAFT` |

---

### `GET /v1/challan/{challan_id}` — Get Challan with Bilties

Returns the challan with an embedded `bilties` array. Each bilty object includes
all fields needed to render a challan manifest — no second API call required.

```json
{
  "challan_id": "...",
  "challan_no": "MUM/0042",
  "status": "OPEN",
  "is_primary": true,
  "total_bilty_count": 5,
  "total_freight": 12500.00,
  "total_weight": 850.5,
  "total_packages": 12,
  "bilties": [
    {
      "bilty_id": "...",
      "gr_no": "GR-001",
      "bilty_date": "2025-04-28",
      "bilty_type": "REGULAR",
      "consignor_name": "ABC Traders",
      "consignor_mobile": "9876543210",
      "consignee_name": "XYZ Stores",
      "consignee_mobile": "9123456789",
      "from_city_id": "...",
      "to_city_id": "...",
      "delivery_type": "DOOR",
      "payment_mode": "TO-PAY",
      "contain": "Electronics",
      "pvt_marks": "FRAGILE / Handle with Care",
      "no_of_pkg": 3,
      "weight": 150.0,
      "actual_weight": 148.5,
      "total_amount": 2500.00,
      "invoice_no": "INV-2025-001",
      "invoice_value": 45000.00,
      "status": "SAVED",
      "challan_assigned_at": "2025-04-28T10:30:00Z"
    }
  ]
}
```

**Embedded bilty fields reference:**

| Field | Description |
|-------|-------------|
| `bilty_id` | UUID of the bilty |
| `gr_no` | GR / LR number |
| `bilty_date` | Date of bilty |
| `bilty_type` | `REGULAR` (from book) or `MANUAL` (hand-written station bilty) |
| `consignor_name` | Sender name (snapshot at creation) |
| `consignor_mobile` | Sender mobile |
| `consignee_name` | Receiver name (snapshot at creation) |
| `consignee_mobile` | Receiver mobile |
| `from_city_id` | Origin city UUID |
| `to_city_id` | Destination city UUID — use city master to resolve name |
| `delivery_type` | `DOOR` or `GODOWN` |
| `payment_mode` | `PAID`, `TO-PAY`, or `FOC` |
| `contain` | Description of goods / contents |
| `pvt_marks` | Private marks / special instructions on the package |
| `no_of_pkg` | Number of packages |
| `weight` | Billed weight |
| `actual_weight` | Physical weight (may differ from billed) |
| `total_amount` | Total freight amount |
| `invoice_no` | Commercial invoice number |
| `invoice_value` | Commercial invoice value |
| `status` | Current bilty status |
| `challan_assigned_at` | Timestamp when this bilty was added to the challan |
```

---

### `PUT /v1/challan/{challan_id}` — Update Challan

**Request body (all optional):**

| Field | Type | Description |
|---|---|---|
| `transport_id` | UUID | Change transport |
| `transport_name` | string | Change transport name |
| `transport_gstin` | string | Change GSTIN |
| `vehicle_info` | object | Replace vehicle details |
| `from_branch_id` | UUID | Correct origin branch |
| `to_branch_id` | UUID | Correct destination branch |
| `challan_date` | string | Correct date |
| `remarks` | string | Update remarks |
| `pdf_url` | string | Store generated PDF URL |
| `metadata` | object | Replace metadata |
| `is_active` | boolean | `false` to soft-delete |

---

### `POST /v1/challan/{challan_id}/set-primary`

Promotes this challan to primary for the current branch.  
Automatically demotes the existing primary.  
**Blocked if** challan is `DISPATCHED`, `ARRIVED_HUB`, or `CLOSED` → `409`.  
No request body needed.

---

### `POST /v1/challan/{challan_id}/dispatch`

Dispatches the challan and **all its bilties simultaneously**.

**Side effects:**
- `challan.status` → `DISPATCHED`
- `challan.is_primary` → `false` (auto-cleared)
- All bilties: `status` → `DISPATCHED`, `is_dispatched` → `true`, `dispatched_challan_no` set

**Blocked if:** challan is already `DISPATCHED`, `ARRIVED_HUB`, or `CLOSED` → `409`.  
No request body needed.

---

### `POST /v1/challan/{challan_id}/arrive-hub`

Marks the challan and all its bilties as arrived at the destination hub.

**Side effects:**
- `challan.status` → `ARRIVED_HUB`
- All bilties: `status` → `REACHED_HUB`, `is_reached_hub` → `true`

**Blocked if:** challan status is not `DISPATCHED` → `409`.  
No request body needed.

---

### `POST /v1/challan/{challan_id}/add-bilty` — Add Bilty to Challan

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `bilty_id` | UUID | ✅ | UUID of the bilty to add |

```json
{ "bilty_id": "uuid-of-bilty" }
```

**Validations:**
- Challan must not be `DISPATCHED`, `ARRIVED_HUB`, or `CLOSED` → `409`
- Bilty must exist and belong to the same company → `404`
- Bilty must not already be on another challan → `409`

**Side effects on the bilty:**
- `bilty.challan_id` → challan UUID
- `bilty.challan_branch_id` → challan's branch
- `bilty.trip_sheet_id` → challan's current trip sheet (if any)
- `bilty.challan_assigned_at` / `challan_assigned_by` set
- Challan totals recalculated (`total_bilty_count`, `total_freight`, `total_weight`, `total_packages`)

---

### `POST /v1/challan/{challan_id}/remove-bilty/{bilty_id}` — Remove Bilty

No request body needed.

**Validations:**
- Challan must not be `DISPATCHED`, `ARRIVED_HUB`, or `CLOSED` → `409`

**Side effects on the bilty:**
- All challan fields cleared (`challan_id`, `challan_branch_id`, `trip_sheet_id`, `challan_assigned_at`, `challan_assigned_by`, `dispatched_challan_no`)
- Challan totals recalculated

---

### `POST /v1/challan/{challan_id}/move-to-trip-sheet` — Assign to Trip Sheet

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `trip_sheet_id` | UUID | ✅ | Target trip sheet UUID |

```json
{ "trip_sheet_id": "uuid-of-trip-sheet" }
```

**Validations:**
- Trip sheet must exist and be `DRAFT` or `OPEN` → `409` otherwise

**Side effects:**
- `challan.trip_sheet_id` → trip sheet UUID
- All bilties on this challan: `bilty.trip_sheet_id` updated
- Trip sheet totals recalculated

---

### `POST /v1/challan/{challan_id}/remove-from-trip-sheet`

Detaches the challan from its current trip sheet. No request body needed.

**Side effects:**
- `challan.trip_sheet_id` → `null`
- All bilties: `bilty.trip_sheet_id` → `null`
- Previous trip sheet totals recalculated

---

## 5. Data Flow

```
Branch books bilties (bilty.challan_id = NULL, status = SAVED/DRAFT)
         │
         ▼
GET /challan/available-bilties      ← fetch list of assignable bilties
         │
         ▼
POST /challan                       ← create challan (is_primary=true)
  challan.status = DRAFT/OPEN
  challan.is_primary = true
         │
         ▼
POST /challan/{id}/add-bilty        ← assign bilties one by one
  bilty.challan_id = challan.challan_id
  bilty.challan_branch_id = challan.branch_id
  bilty.trip_sheet_id = challan.trip_sheet_id (if already on a sheet)
  challan totals recalculated
         │
         ▼ (optional)
POST /trip-sheet                    ← create company-level trip sheet
POST /challan/{id}/move-to-trip-sheet
  challan.trip_sheet_id = trip_sheet_id
  all bilties.trip_sheet_id updated
  trip sheet totals recalculated
         │
         ▼
POST /challan/{id}/dispatch         ← end of day / truck departs
  challan.status = DISPATCHED
  challan.is_primary = false  ← auto-cleared
  all bilties: status = DISPATCHED, is_dispatched = true
         │
         ▼
POST /challan/{id}/arrive-hub       ← truck arrives at destination hub
  challan.status = ARRIVED_HUB
  all bilties: status = REACHED_HUB
```

---

## 6. Status Machines

### Challan Status

```
DRAFT ──► OPEN ──► DISPATCHED ──► ARRIVED_HUB ──► CLOSED
```

| Status | Can add/remove bilties | Can set as primary | Can move to trip sheet |
|---|---|---|---|
| `DRAFT` | ✅ | ✅ | ✅ |
| `OPEN` | ✅ | ✅ | ✅ |
| `DISPATCHED` | ❌ | ❌ | ❌ |
| `ARRIVED_HUB` | ❌ | ❌ | ❌ |
| `CLOSED` | ❌ | ❌ | ❌ |

### Trip Sheet Status

```
DRAFT ──► OPEN ──► DISPATCHED ──► ARRIVED ──► CLOSED
```

| Status | Can receive challans |
|---|---|
| `DRAFT` | ✅ |
| `OPEN` | ✅ |
| `DISPATCHED` | ❌ |
| `ARRIVED` | ❌ |
| `CLOSED` | ❌ |

### Bilty Status (challan-driven transitions)

| Challan action | Bilty fields updated |
|---|---|
| `add-bilty` | `challan_id`, `challan_branch_id`, `trip_sheet_id`, `challan_assigned_at/by` set |
| `remove-bilty` | All challan fields cleared |
| `dispatch` | `status=DISPATCHED`, `is_dispatched=true`, `dispatched_at/by`, `dispatched_challan_no` |
| `arrive-hub` | `status=REACHED_HUB`, `is_reached_hub=true`, `reached_hub_at/by` |

---

## 7. Primary Challan Feature

Each branch can designate **one open challan** as its **primary challan**. This is the "current active challan of the day" concept.

### How It Works

1. At the start of the day, create a challan with `"is_primary": true`
2. Frontend polls `GET /v1/challan/primary` to know the active challan
3. When booking bilties, the frontend can auto-call `add-bilty` on the primary challan
4. At end of day, dispatch the challan → `is_primary` is auto-cleared
5. Next day, create a new challan and set as primary

### Uniqueness Enforcement

The DB enforces **at most one primary** per company+branch via a partial unique index:

```sql
UNIQUE ON challan(company_id, branch_id)
WHERE is_primary = TRUE
  AND is_active = TRUE
  AND status NOT IN ('DISPATCHED', 'ARRIVED_HUB', 'CLOSED')
```

The application also unsets the existing primary before setting a new one (double safety).

### Rules

- Only `DRAFT` or `OPEN` challans can be set as primary → `409` otherwise
- Dispatching auto-clears `is_primary`
- Soft-deleting (`is_active=false`) does not clear primary — use `/set-primary` on another challan first

---

## 8. Error Reference

| HTTP Code | When |
|---|---|
| `400` | Bad request — e.g. challan number generation failed, invalid input |
| `401` | Missing or invalid JWT |
| `404` | Resource not found (challan, bilty, book, trip sheet, template) |
| `409` | Conflict — e.g. bilty already assigned, challan already dispatched, wrong status for action |
| `410` | Challan book exhausted — all numbers in the series have been used |
| `422` | Validation error — e.g. `FIXED_ROUTE` without branch IDs, `from_number > to_number` |
| `500` | Unexpected server error |

### Common 409 Scenarios

| Action | 409 reason |
|---|---|
| `add-bilty` | Challan is `DISPATCHED`/`ARRIVED_HUB`/`CLOSED` |
| `add-bilty` | Bilty already has a `challan_id` |
| `dispatch` | Challan is already `DISPATCHED`/`ARRIVED_HUB`/`CLOSED` |
| `arrive-hub` | Challan is not in `DISPATCHED` status |
| `set-primary` | Challan is `DISPATCHED`/`ARRIVED_HUB`/`CLOSED` |
| `move-to-trip-sheet` | Trip sheet is `DISPATCHED`/`ARRIVED`/`CLOSED` |
