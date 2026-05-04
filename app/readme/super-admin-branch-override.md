# Branch Override — Frontend Integration Guide

Any authenticated user can operate under a **different branch** within their company
by passing `branch_id` in the request body (POST/PATCH/PUT) or as a query parameter (GET).

If `branch_id` is omitted, the user's own JWT branch is used automatically.

> **Security:** `company_id` is always taken from the JWT and cannot be overridden.
> A user can only access branches within their own company.

---

## How It Works

```
branch_id provided in request  →  use that branch
branch_id omitted              →  use JWT branch (user's own branch)
```

No role check — any user who knows a branch UUID within their company can use it.

---

## Affected Endpoints

| Method | Endpoint | How to pass `branch_id` |
|--------|----------|------------------------|
| `GET` | `/v1/bilty-setting/books` | Query param: `?branch_id=<uuid>` |
| `POST` | `/v1/bilty-setting/books` | Request body field |
| `PATCH` | `/v1/bilty-setting/books/{book_id}` | (immutable after creation) |
| `GET` | `/v1/challan/book` | Query param: `?branch_id=<uuid>` |
| `POST` | `/v1/challan/book` | Request body field |
| `POST` | `/v1/challan` | Request body field |

---

## Bilty Book — Full Field Reference

### `POST /v1/bilty-setting/books`

```json
{
  "branch_id": "128e4335-7fef-4f2e-9843-609fda142d27",

  "book_name":    "HO-MANUAL-FY26",
  "bilty_type":   "REGULAR",   // "REGULAR" | "MANUAL"
  "party_scope":  "COMMON",    // "COMMON" | "CONSIGNOR" | "CONSIGNEE"
  "consignor_id": null,        // required when party_scope=CONSIGNOR
  "consignee_id": null,        // required when party_scope=CONSIGNEE

  "prefix":       "MUM/",
  "from_number":  1,           // required for REGULAR; omit for MANUAL
  "to_number":    500,         // required for REGULAR; omit for MANUAL
  "digits":       4,           // zero-pad width → "0001"
  "postfix":      "/26",

  "is_fixed":      false,      // true = same number reused every time
  "auto_continue": false,      // true = auto-create next book when exhausted

  "template_id":   null,       // UUID of bilty_template for printing
  "template_name": null,       // human label (informational)

  "book_defaults": {
    "delivery_type":         "GODOWN",
    "payment_mode":          "TO-PAY",
    "from_city_id":          "<city-uuid>",
    "to_city_id":            null,
    "transport_id":          null,
    "bill_charge":           null,
    "toll_charge":           null,
    "show_invoice":          false,
    "show_eway_bill":        true,
    "show_itemized_charges": false,
    "show_pvt_marks":        true,
    "show_contain":          false
  },
  "metadata": {}
}
```

### `GET /v1/bilty-setting/books`

```
# Own branch (default)
GET /v1/bilty-setting/books

# Another branch
GET /v1/bilty-setting/books?branch_id=128e4335-7fef-4f2e-9843-609fda142d27

# Filters (combinable)
GET /v1/bilty-setting/books?branch_id=<uuid>&bilty_type=MANUAL&is_active=true
```

### `PATCH /v1/bilty-setting/books/{book_id}` — updatable fields only

```json
{
  "book_name":     "HO-MANUAL-FY26-UPDATED",
  "template_id":   null,
  "template_name": null,
  "is_fixed":      false,
  "auto_continue": true,
  "is_active":     true,
  "is_completed":  false,
  "book_defaults": { "...": "..." },
  "metadata":      {}
}
```

> `from_number`, `to_number`, `prefix`, `postfix`, `digits`, `branch_id` are
> **immutable** after creation.

---

## Challan Book — Full Field Reference

### `POST /v1/challan/book`

```json
{
  "branch_id": "128e4335-7fef-4f2e-9843-609fda142d27",

  "book_name":  "HO-CHALLAN-FY26",
  "template_id": null,

  "route_scope":    "OPEN",       // "OPEN" | "FIXED_ROUTE"
  "from_branch_id": null,         // required when route_scope=FIXED_ROUTE
  "to_branch_id":   null,         // required when route_scope=FIXED_ROUTE

  "prefix":      "CH/",
  "from_number": 1,
  "to_number":   1000,
  "digits":      4,
  "postfix":     null,

  "is_fixed":      false,
  "auto_continue": false,
  "is_primary":    false,
  "metadata":      {}
}
```

### `GET /v1/challan/book`

```
# Own branch (default)
GET /v1/challan/book

# Another branch
GET /v1/challan/book?branch_id=128e4335-7fef-4f2e-9843-609fda142d27
```

---

## Challan — Full Field Reference

### `POST /v1/challan`

```json
{
  "branch_id": "128e4335-7fef-4f2e-9843-609fda142d27",

  "challan_no":    null,     // omit to auto-claim from primary book
  "book_id":       null,     // specific book; falls back to primary if omitted
  "trip_sheet_id": null,
  "template_id":   null,

  "from_branch_id": "<origin-branch-uuid>",
  "to_branch_id":   "<dest-branch-uuid>",

  "transport_id":    null,
  "transport_name":  "RGT LOGISTICS",
  "transport_gstin": null,

  "fleet_id":     null,
  "driver_id":    null,
  "owner_id":     null,
  "conductor_id": null,

  "vehicle_info": {},
  "challan_date": null,
  "remarks":      null,
  "is_primary":   false,
  "metadata":     {}
}
```

---

## Frontend Usage Pattern

```js
// Show branch selector only when user wants to create for another branch
const payload = {
  ...formData,
  branch_id: selectedBranchId !== currentUser.branch_id
    ? selectedBranchId
    : undefined,   // omit → backend uses JWT branch
};

await api.post('/v1/bilty-setting/books', payload);
```


`super_admin` users (identified by `post_in_office == "super_admin"` in the JWT) can
create and manage resources under **any branch** in their company by passing
`branch_id` in the request body.

Regular users always operate under their own JWT branch — the `branch_id` field
in the body is silently ignored for them.

---

## Affected Endpoints

| Method | Path | What `branch_id` controls |
|--------|------|--------------------------|
| `POST` | `/v1/bilty-setting/books` | Which branch the bilty book belongs to |
| `PATCH` | `/v1/bilty-setting/books/{book_id}` | (field accepted but not patched — use POST to create under target branch) |
| `POST` | `/v1/challan/book` | Which branch the challan book belongs to |
| `PUT` | `/v1/challan/book/{book_id}` | (field accepted but not patched — use POST to create under target branch) |
| `POST` | `/v1/challan` | Which branch the challan is created under |

---

## Bilty Book — Full Field Reference

### `POST /v1/bilty-setting/books`

```json
{
  "branch_id": "128e4335-7fef-4f2e-9843-609fda142d27",  // super_admin only

  "book_name":    "HO-MANUAL-FY26",
  "bilty_type":   "REGULAR",   // "REGULAR" | "MANUAL"
  "party_scope":  "COMMON",    // "COMMON" | "CONSIGNOR" | "CONSIGNEE"
  "consignor_id": null,        // required when party_scope=CONSIGNOR
  "consignee_id": null,        // required when party_scope=CONSIGNEE

  "prefix":       "MUM/",
  "from_number":  1,           // required for REGULAR; omit for MANUAL
  "to_number":    500,         // required for REGULAR; omit for MANUAL
  "digits":       4,           // zero-pad width → "0001"
  "postfix":      "/26",

  "is_fixed":      false,      // true = same number reused every time
  "auto_continue": false,      // true = auto-create next book when exhausted

  "template_id":  null,        // UUID of bilty_template to use for printing
  "template_name": null,       // human label (informational)

  "book_defaults": {
    "delivery_type":  "GODOWN",   // "DOOR" | "GODOWN"
    "payment_mode":   "TO-PAY",   // "PAID" | "TO-PAY" | "FOC"
    "from_city_id":   "f416e290-b5c1-47d3-a4e3-fe174a99540f",
    "to_city_id":     null,
    "transport_id":   null,
    "bill_charge":    null,
    "toll_charge":    null,
    "show_invoice":         false,
    "show_eway_bill":       true,
    "show_itemized_charges": false,
    "show_pvt_marks":       true,
    "show_contain":         false
  },
  "metadata": {}
}
```

### `PATCH /v1/bilty-setting/books/{book_id}` — updatable fields only

```json
{
  "book_name":     "HO-MANUAL-FY26-UPDATED",
  "template_id":   null,
  "template_name": null,
  "is_fixed":      false,
  "auto_continue": true,
  "is_active":     true,
  "is_completed":  false,
  "book_defaults": { ... },
  "metadata":      {}
}
```

> Number range (`from_number`, `to_number`, `prefix`, `postfix`, `digits`) is
> **immutable** after creation — create a new book if the range needs to change.

---

## Challan Book — Full Field Reference

### `POST /v1/challan/book`

```json
{
  "branch_id": "128e4335-7fef-4f2e-9843-609fda142d27",  // super_admin only

  "book_name":  "HO-CHALLAN-FY26",
  "template_id": null,

  "route_scope":    "OPEN",          // "OPEN" | "FIXED_ROUTE"
  "from_branch_id": null,            // required when route_scope=FIXED_ROUTE
  "to_branch_id":   null,            // required when route_scope=FIXED_ROUTE

  "prefix":      "CH/",
  "from_number": 1,
  "to_number":   1000,
  "digits":      4,
  "postfix":     null,

  "is_fixed":      false,
  "auto_continue": false,
  "is_primary":    false,
  "metadata":      {}
}
```

### `PUT /v1/challan/book/{book_id}` — updatable fields only

```json
{
  "book_name":      "HO-CHALLAN-FY26-B",
  "template_id":    null,
  "from_branch_id": null,
  "to_branch_id":   null,
  "is_fixed":       false,
  "auto_continue":  true,
  "is_active":      true,
  "is_primary":     false,
  "metadata":       {}
}
```

---

## Challan — Full Field Reference

### `POST /v1/challan`

```json
{
  "branch_id": "128e4335-7fef-4f2e-9843-609fda142d27",  // super_admin only

  "challan_no":    null,    // omit to auto-claim from primary book
  "book_id":       null,    // specify to use a particular book instead of primary
  "trip_sheet_id": null,
  "template_id":   null,

  "from_branch_id": "0c15b4c4-3d14-4c68-af43-c8ce7e738fd7",
  "to_branch_id":   "128e4335-7fef-4f2e-9843-609fda142d27",

  "transport_id":   null,
  "transport_name": "RGT LOGISTICS",
  "transport_gstin": null,

  "fleet_id":     null,   // fleet.fleet_id (registered vehicle)
  "driver_id":    null,   // fleet_staff.staff_id with role=DRIVER
  "owner_id":     null,   // fleet_staff.staff_id with role=OWNER
  "conductor_id": null,   // fleet_staff.staff_id with role=CONDUCTOR

  "vehicle_info": {},     // legacy free-form vehicle snapshot
  "challan_date": null,   // ISO date string; defaults to today
  "remarks":      null,
  "is_primary":   false,
  "metadata":     {}
}
```

---

## How the Override Works (Backend Logic)

```python
def _resolve_branch(user, body_branch_id):
    if body_branch_id and user["post_in_office"] == "super_admin":
        return body_branch_id   # use the body value
    return user["branch_id"]    # always JWT branch for regular users
```

- The `company_id` is **always** taken from the JWT — a super_admin cannot
  create resources under a different company.
- If `branch_id` is omitted by a super_admin, their own JWT branch is used.
