# Bilty Module — Frontend Integration Guide

This document covers every API call needed to build the Bilty screen in the frontend.  
All endpoints require `Authorization: Bearer <token>`.  
All data is automatically scoped to the logged-in user's `company_id` and `branch_id`.

---

## Screen Map

```
Bilty
├── 1. Create Bilty
├── 2. Edit Bilty   (recent list → click → auto-fill form)
└── 3. Cancel Bilty
```

---

## Base URL

```
http://<your-server>/v1
```

---

---

# 1. CREATE BILTY

## Full flow (step by step)

### Step 1A — Load dropdowns AND fetch primary book + template (run once when screen opens)

Run all five calls in parallel when the screen mounts.

```
GET /v1/bilty-setting/consignors?is_active=true
GET /v1/bilty-setting/consignees?is_active=true
GET /v1/master/cities?is_active=true
GET /v1/master/transports?is_active=true
```

> **No book dropdown, no template dropdown.** The backend auto-picks the primary book and primary template when you create a bilty. You only need to fetch them to display the GR preview and know which print template to use.

#### Fetch the primary book (for GR preview display + form pre-fill)

```
GET /v1/bilty-setting/books/primary?bilty_type=REGULAR
```

**Response:**
```json
{
  "book_id":        "9c8e1949-c616-4f4d-995b-1508c989d232",
  "book_name":      "Main Book 2025-26",
  "bilty_type":     "REGULAR",
  "prefix":         "TST/",
  "postfix":        "",
  "digits":         4,
  "current_number": 10,
  "from_number":    1,
  "to_number":      500,
  "is_primary":     true,
  "is_active":      true,
  "is_completed":   false,
  "template_id":    "40663dbb-7cff-45a9-8100-8c7a683c6fd1",
  "book_defaults": {
    "delivery_type": "GODOWN",
    "payment_mode":  "TO-PAY",
    "from_city_id":  "0fb3a1fd-933b-46fa-b7d8-1bab7a99e43d"
  }
}
```

Use this to:
1. Compute the **GR preview** (display only):
```js
const grPreview = (book.prefix ?? '')
               + String(book.current_number).padStart(book.digits, '0')
               + (book.postfix ?? '')
// e.g. → "TST/0010"
```

2. **Pre-fill form fields** from `book_defaults`:
```js
const d = book.book_defaults ?? {}
form.delivery_type = d.delivery_type ?? ''    // e.g. "GODOWN"
form.payment_mode  = d.payment_mode  ?? ''    // e.g. "TO-PAY"
form.from_city_id  = d.from_city_id  ?? null  // e.g. "0fb3a1fd-..." (ALIGARH)
form.to_city_id    = d.to_city_id    ?? null  // optional default destination
form.transport_id  = d.transport_id  ?? null  // optional default transporter
```

The user can still change any pre-filled value before saving. These are just defaults.

> If this returns **404**, no primary book has been set. Show:  
> *"Go to Settings → Books and mark one as primary before creating bilties."*

#### Fetch the primary template (for PDF rendering)

```
GET /v1/bilty-setting/templates/primary
```

**Response:**
```json
{
  "template_id":  "40663dbb-7cff-45a9-8100-8c7a683c6fd1",
  "code":         "A4_FIRST",
  "name":         "Standard A4",
  "slug":         "first-a4-template",
  "metadata": {
    "ADDRESS":   "DELHI",
    "TRANSPORT": "RGT LOGISTICS"
  },
  "is_primary":   true,
  "is_active":    true
}
```

Store `template_id` and `metadata` locally — you'll pass `metadata` together with the bilty data into jsPDF to render the PDF after save.

> If this returns **404**, no primary template is set. You can still create bilties — they'll have no `template_id` — but printing won't have a template.

**City response shape:**
```json
{
  "count": 42,
  "cities": [
    {
      "city_id":    "<uuid>",
      "city_name":  "Mumbai",
      "city_code":  "MUM",
      "state_id":   "<uuid>",
      "is_active":  true
    }
  ]
}
```

**Transport response shape:**
```json
{
  "count": 8,
  "transports": [
    {
      "transport_id":   "<uuid>",
      "transport_name": "Rajdhani Transport",
      "gstin":          "27AABCT1234Z5",
      "mobile":         "9876543210",
      "is_active":      true
    }
  ]
}
```

**Tip — city search / filter by state:**
```
GET /v1/master/cities?state_id=<state_uuid>&is_active=true
```

---

### Step 1B — Screen opens → Show GR preview (no user action needed)

The GR preview is computed from the primary book fetched above. No dropdown, no user selection.

```js
// Already computed in Step 1A:
form.gr_no_preview = grPreview   // "TST/0010" — display only, NOT sent to API
```

---

### Step 1C — User fills form and clicks Save → Backend auto-claims GR

**You do NOT need to call `/next-gr` manually.** Just send `POST /v1/bilty` without `gr_no` or `book_id` — the backend will:
1. Auto-pick the primary REGULAR book for the branch
2. Atomically claim the next GR number
3. Auto-apply the primary template

> ⚠️ The GR is consumed inside the `POST /v1/bilty` call itself. Do not call `/next-gr` separately before saving — that would consume a number even if the save fails.

> **When to use `/next-gr` manually:**  
> Only if you want to show the user the *confirmed* GR number before they see the success screen (e.g. for re-confirmation dialogs). In that case call `GET /v1/bilty/next-gr` (no path param — uses primary book) and pass the returned `gr_no` + `book_id` in the POST body.
```
GET /v1/bilty/next-gr
```
**Response:**
```json
{
  "gr_no":     "TST/0010",
  "gr_number": 10,
  "book_id":   "9c8e1949-..."
}
```
> ⚠️ This call **immediately consumes** the number. Only call it if you will definitely follow with `POST /v1/bilty`.

---

### Step 1D — Create the bilty

```
POST /v1/bilty
Content-Type: application/json
Authorization: Bearer <token>
```

**Request body — omit `gr_no`, `book_id`, `template_id` entirely (backend fills them automatically):**
```json
{
  "bilty_type":       "REGULAR",
  "bilty_date":       "2026-04-27",

  "consignor_id":     "fdccadc0-...",
  "consignor_name":   "Sharma Traders",
  "consignor_gstin":  "27AABCS1234Z5",
  "consignor_mobile": "9000000000",

  "consignee_id":     "0795c6d7-...",
  "consignee_name":   "Delhi Distributors",
  "consignee_gstin":  null,
  "consignee_mobile": "8000000010",

  "transport_id":     null,
  "transport_name":   "Rajdhani Transport",
  "transport_mobile": null,

  "from_city_id":     "<city_uuid>",
  "to_city_id":       "<city_uuid>",

  "delivery_type":    "DOOR",
  "payment_mode":     "PAID",
  "contain":          "Electronics",
  "invoice_no":       "INV-2026-001",
  "invoice_value":    15000,
  "invoice_date":     "2026-04-26",
  "e_way_bills":      [{ "ewb_no": "1234567890123", "valid_upto": "2026-05-10" }],
  "no_of_pkg":        5,
  "weight":           52.5,
  "actual_weight":    52.5,
  "rate":             8.0,

  "freight_amount":   420.0,
  "labour_charge":    50.0,
  "bill_charge":      10.0,
  "local_charge":     0.0,
  "toll_charge":      0.0,
  "dd_charge":        0.0,
  "pf_charge":        0.0,
  "other_charge":     0.0,
  "discount_percentage": 0.0,
  "discount_amount":  0.0,
  "total_amount":     480.0,

  "saving_option":    "SAVE",
  "status":           "SAVED",
  "remark":           ""
}
```

The response will include the auto-assigned `gr_no`, `book_id`, and `template_id`:

**Response (201):**
```json
{
  "message": "Bilty created.",
  "bilty": {
    "bilty_id":      "abc123-...",
    "gr_no":         "TST/0010",
    "book_id":       "9c8e1949-...",
    "template_id":   "40663dbb-...",
    "bilty_date":    "2026-04-27",
    "consignor_name":"Sharma Traders",
    "consignee_name":"Delhi Distributors",
    "total_amount":  480.0,
    "status":        "SAVED"
  }
}
```

### After save — trigger print, reset form, and refresh GR preview

This is the correct post-save sequence.

```
Step 1 — Trigger print using the template metadata fetched at screen open
Step 2 — Reset the form
Step 3 — Re-fetch the primary book to get the updated current_number → recompute GR preview
```

**Step 1 — Trigger print**

You already have the primary template's `metadata` from Step 1A. Fetch the full bilty and pass both into jsPDF:

```js
const biltyId = response.bilty.bilty_id

// Fetch full bilty for PDF data
const bilty = await GET(`/v1/bilty/${biltyId}`)

// Render PDF using the template metadata loaded at screen open
generatePDF(bilty, primaryTemplate.metadata)
```

> If you need the template metadata fresh (e.g. it may have changed), re-fetch it:
> ```js
> const tmpl = await GET('/v1/bilty-setting/templates/primary')
> generatePDF(bilty, tmpl.metadata)
> ```

**Step 2 — Reset the form completely**

```js
resetForm()    // clear all fields to blank/default values
```

> Do NOT keep the old `gr_no` in the form after save. That number was consumed.

**Step 3 — Re-fetch the primary book and recompute the GR preview**

After save the book's `current_number` has advanced by 1. Re-fetch via the primary endpoint:

```js
// Always use the primary endpoint — no need to track a book_id anywhere
const freshBook = await GET('/v1/bilty-setting/books/primary?bilty_type=REGULAR')

form.gr_no_preview = (freshBook.prefix ?? '')
                   + String(freshBook.current_number).padStart(freshBook.digits, '0')
                   + (freshBook.postfix ?? '')
```

**Complete post-save handler (pseudocode):**

```js
async function onSaveSuccess(response) {
  // 1. Print
  const bilty = await GET(`/v1/bilty/${response.bilty.bilty_id}`)
  generatePDF(bilty, primaryTemplate.metadata)   // primaryTemplate loaded at screen open

  // 2. Reset form
  resetForm()

  // 3. Refresh primary book → recompute GR preview
  primaryBook = await GET('/v1/bilty-setting/books/primary?bilty_type=REGULAR')
  form.gr_no_preview = (primaryBook.prefix ?? '')
                     + String(primaryBook.current_number).padStart(primaryBook.digits, '0')
                     + (primaryBook.postfix ?? '')
}
```

> **Why re-fetch instead of incrementing locally?**  
> Another user on another tab may have created a bilty between your save and the next form open.  
> Always get `current_number` fresh from the server.

---

### MANUAL bilty (no book)

For station bilties where the GR is hand-written, set `bilty_type=MANUAL` and provide `gr_no` yourself:

```json
{
  "gr_no":       "MAN-2026-001",
  "bilty_type":  "MANUAL",
  ...
}
```

`book_id` is not required and not auto-filled for MANUAL bilties. Show a plain text input for `gr_no` instead of the computed preview.

---

---

# 2. EDIT BILTY

## Step 2A — Load recent bilties list

```
GET /v1/bilty?limit=50&offset=0
```

**Optional filters** (bind to UI filter bar):

| Query param | Type | Example | What it filters |
|---|---|---|---|
| `status` | string | `SAVED` | Lifecycle status |
| `payment_mode` | string | `PAID` | Payment type |
| `consignor_id` | UUID | `fdccadc0-...` | By shipper |
| `consignee_id` | UUID | `0795c6d7-...` | By receiver |
| `from_date` | ISO date | `2026-04-01` | Bilty date range start |
| `to_date` | ISO date | `2026-04-30` | Bilty date range end |
| `bilty_type` | string | `REGULAR` | REGULAR or MANUAL |
| `limit` | int | `50` | Page size (max 500) |
| `offset` | int | `0` | Pagination offset |

**Response:**
```json
{
  "count": 9,
  "bilties": [
    {
      "bilty_id":       "abc123-...",
      "gr_no":          "TST/0009",
      "bilty_date":     "2026-04-27",
      "consignor_name": "Patel Enterprises",
      "consignee_name": "Chennai Clearing",
      "payment_mode":   "PAID",
      "total_amount":   2700.0,
      "status":         "SAVED",
      "no_of_pkg":      6,
      "weight":         63.0,
      "from_city_id":   null,
      "to_city_id":     null
    },
    ...
  ]
}
```

**Recommended card display fields:**

```
GR No       │ TST/0009
Date        │ 27 Apr 2026
Consignor   │ Patel Enterprises
Consignee   │ Chennai Clearing
Pkgs / Wt   │ 6 pkgs • 63 kg
Amount      │ ₹2,700
Status      │ SAVED  (badge)
Payment     │ PAID   (badge)
```

---

## Step 2B — User clicks a bilty card → Auto-fill the form

```
GET /v1/bilty/{bilty_id}
```

**Response** is the full bilty object. Map each field directly to your form:

```js
// Example mapping (React / Vue / Angular)
form.gr_no            = bilty.gr_no
form.bilty_date       = bilty.bilty_date

// Consignor
form.consignor_id     = bilty.consignor_id
form.consignor_name   = bilty.consignor_name
form.consignor_gstin  = bilty.consignor_gstin
form.consignor_mobile = bilty.consignor_mobile

// Consignee
form.consignee_id     = bilty.consignee_id
form.consignee_name   = bilty.consignee_name
form.consignee_gstin  = bilty.consignee_gstin
form.consignee_mobile = bilty.consignee_mobile

// Transport — pre-select the dropdown by transport_id, display transport_name
form.transport_id     = bilty.transport_id
form.transport_name   = bilty.transport_name
form.transport_gstin  = bilty.transport_gstin
form.transport_mobile = bilty.transport_mobile

// Cities — pre-select dropdowns by city_id, display city_name (resolve from cached list)
form.from_city_id     = bilty.from_city_id
form.to_city_id       = bilty.to_city_id

// All charge fields
form.payment_mode     = bilty.payment_mode
form.delivery_type    = bilty.delivery_type
form.no_of_pkg        = bilty.no_of_pkg
form.weight           = bilty.weight
form.rate             = bilty.rate
form.freight_amount   = bilty.freight_amount
form.labour_charge    = bilty.labour_charge
form.bill_charge      = bilty.bill_charge
form.toll_charge      = bilty.toll_charge
form.dd_charge        = bilty.dd_charge
form.pf_charge        = bilty.pf_charge
form.other_charge     = bilty.other_charge
form.total_amount     = bilty.total_amount
form.contain          = bilty.contain
form.invoice_no       = bilty.invoice_no
form.invoice_value    = bilty.invoice_value
form.invoice_date     = bilty.invoice_date
form.e_way_bill       = bilty.e_way_bill
form.remark           = bilty.remark
```

> GR number and `bilty_type` are **read-only** in edit mode — never let the user change them.  
> `book_id` is also immutable.

---

## Step 2C — User edits fields and clicks Update

Send only the changed fields (PATCH is partial update):

```
PATCH /v1/bilty/{bilty_id}
Content-Type: application/json
Authorization: Bearer <token>
```

**Request body (send only what changed):**
```json
{
  "consignee_name":  "Delhi Distributors Updated",
  "total_amount":    520.0,
  "freight_amount":  460.0,
  "remark":          "Updated weight after recount"
}
```

**Response (200):**
```json
{
  "message": "Bilty updated.",
  "bilty": { ...full updated bilty object... }
}
```

---

---

# 3. CANCEL BILTY

```
DELETE /v1/bilty/{bilty_id}
Content-Type: application/json
Authorization: Bearer <token>
```

**Request body (reason is mandatory):**
```json
{
  "deletion_reason": "Wrong consignee entered — re-booking under correct party"
}
```

**Response (200):**
```json
{
  "message": "Bilty cancelled.",
  "bilty": {
    "bilty_id":        "...",
    "status":          "CANCELLED",
    "is_active":       false,
    "deleted_at":      "2026-04-27T08:15:00Z",
    "deletion_reason": "Wrong consignee entered — re-booking under correct party"
  }
}
```

Cancelled bilties are never hard-deleted. They remain visible with `is_active=false`.  
To show cancelled bilties in the list use `?is_active=false`.

---

---

# GR Number — Full Lifecycle Reference

```
Book created, marked as primary
   current_number = 1

Screen opens
   GET /v1/bilty-setting/books/primary?bilty_type=REGULAR
   GET /v1/bilty-setting/templates/primary
   preview GR = "TST/" + "0001"  (computed client-side, NOT consumed)

User fills form and clicks Save
   POST /v1/bilty  { bilty_type: "REGULAR", consignor_name: ..., ... }
   ↳ backend auto-picks primary book
   ↳ backend atomically claims next GR  ← number consumed here
   ↳ backend auto-applies primary template
   → { bilty_id: "...", gr_no: "TST/0001", book_id: "...", template_id: "..." }
   current_number now = 2

GET /v1/bilty/{bilty_id}
   → full bilty for jsPDF render

After print / reset:
   GET /v1/bilty-setting/books/primary?bilty_type=REGULAR
   → current_number = 2  →  new preview = "TST/0002"
```

---

# Quick Endpoint Reference

| Action | Method | URL |
|---|---|---|
| **Get primary book** (GR preview + auto-pick) | GET | `/v1/bilty-setting/books/primary?bilty_type=REGULAR` |
| **Set a book as primary** | PATCH | `/v1/bilty-setting/books/{book_id}/set-primary` |
| **Get primary template** (PDF metadata) | GET | `/v1/bilty-setting/templates/primary` |
| **Set a template as primary** | PATCH | `/v1/bilty-setting/templates/{template_id}/set-primary` |
| List consignors (for dropdown) | GET | `/v1/bilty-setting/consignors?is_active=true` |
| List consignees (for dropdown) | GET | `/v1/bilty-setting/consignees?is_active=true` |
| List cities (From/To City dropdown) | GET | `/v1/master/cities?is_active=true` |
| List cities filtered by state | GET | `/v1/master/cities?state_id=<uuid>&is_active=true` |
| Get single city | GET | `/v1/master/cities/{city_id}` |
| List transports (Transporter dropdown) | GET | `/v1/master/transports?is_active=true` |
| Get single transport | GET | `/v1/master/transports/{transport_id}` |
| Claim next GR from primary book (optional) | GET | `/v1/bilty/next-gr` |
| Claim next GR from a specific book (optional) | GET | `/v1/bilty/next-gr/{book_id}` |
| **Create bilty** (auto GR + auto template) | POST | `/v1/bilty` |
| List bilties (for edit list) | GET | `/v1/bilty` |
| Get full bilty (for edit auto-fill / print) | GET | `/v1/bilty/{bilty_id}` |
| Update bilty | PATCH | `/v1/bilty/{bilty_id}` |
| Cancel bilty | DELETE | `/v1/bilty/{bilty_id}` |

---

# Field Reference — Create Bilty

| Field | Required | Type | Allowed values / notes |
|---|---|---|---|
| `bilty_type` | ✓ | string | `REGULAR` or `MANUAL` |
| `gr_no` | ✗ for REGULAR | string | **Omit** — backend auto-claims from primary book. Required only for `MANUAL`. |
| `book_id` | ✗ for REGULAR | UUID | **Omit** — backend auto-fills from primary book. |
| `template_id` | ✗ | UUID | **Omit** — backend auto-fills from primary template. |
| `bilty_date` | | ISO date | Default: today |
| `consignor_id` | | UUID | From consignors dropdown |
| `consignor_name` | ✓ | string | Snapshot at save time |
| `consignor_gstin` | | string | max 15 chars |
| `consignor_mobile` | | string | |
| `consignee_id` | | UUID | From consignees dropdown |
| `consignee_name` | | string | Snapshot at save time |
| `consignee_gstin` | | string | |
| `consignee_mobile` | | string | |
| `transport_id` | | UUID | From `/v1/master/transports` dropdown |
| `transport_name` | | string | Snapshot — auto-fill from selected transport |
| `transport_gstin` | | string | Snapshot — auto-fill from selected transport |
| `from_city_id` | | UUID | From `/v1/master/cities` dropdown |
| `to_city_id` | | UUID | From `/v1/master/cities` dropdown |
| `delivery_type` | | string | `DOOR` or `GODOWN` |
| `payment_mode` | | string | `PAID`, `TO-PAY`, `FOC` |
| `contain` | | string | Goods description |
| `invoice_no` | | string | |
| `invoice_value` | | number | |
| `invoice_date` | | ISO date | |
| `e_way_bill` | | object | `{ ewb_no, valid_upto }` |
| `document_number` | | string | |
| `no_of_pkg` | | integer | |
| `weight` | | number | kg |
| `rate` | | number | per kg or per pkg |
| `pvt_marks` | | string | |
| `freight_amount` | | number | |
| `labour_rate` | | number | |
| `labour_charge` | | number | |
| `bill_charge` | | number | |
| `toll_charge` | | number | |
| `dd_charge` | | number | Door delivery charge |
| `pf_charge` | | number | Packing/forwarding |
| `other_charge` | | number | |
| `total_amount` | | number | Sum of all charges |
| `saving_option` | | string | `SAVE`, `DRAFT`, `PRINT` |
| `status` | | string | `SAVED` (default) or `DRAFT` |
| `remark` | | string | |

---

# Status Badge Colors (suggested)

| Status | Color |
|---|---|
| `DRAFT` | Grey |
| `SAVED` | Blue |
| `DISPATCHED` | Indigo |
| `REACHED_HUB` | Purple |
| `AT_GODOWN` | Orange |
| `OUT_FOR_DELIVERY` | Amber |
| `DELIVERED` | Green |
| `UNDELIVERED` | Red |
| `CANCELLED` | Red / strikethrough |
| `LOST` | Dark red |

---

# Payment Mode Badge Colors (suggested)

| Payment mode | Color |
|---|---|
| `PAID` | Green |
| `TO-PAY` | Orange |
| `FOC` | Blue |

---

# Pagination Pattern

```
// Page 1
GET /v1/bilty?limit=50&offset=0

// Page 2
GET /v1/bilty?limit=50&offset=50

// Page 3
GET /v1/bilty?limit=50&offset=100
```

The `count` field in the response is the number of records returned in that page (not total).  
To detect "no more pages": if `count < limit`, you are on the last page.
