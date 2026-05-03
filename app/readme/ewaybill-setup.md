# E-Way Bill API — Complete Technical Reference

## Table of Contents
1. [What is Masters India?](#1-what-is-masters-india)
2. [Credentials — ID & Password](#2-credentials--id--password)
3. [Authentication & JWT Token](#3-authentication--jwt-token)
4. [Token File — How It Looks](#4-token-file--how-it-looks)
5. [Token Validation Flow](#5-token-validation-flow)
6. [Request Header Structure](#6-request-header-structure)
7. [API Endpoint Map](#7-api-endpoint-map)
8. [Fetch E-Way Bill Details](#8-fetch-e-way-bill-details)
9. [GSTIN Validator](#9-gstin-validator)
10. [Transporter Details Lookup](#10-transporter-details-lookup)
11. [Distance Between Pincodes](#11-distance-between-pincodes)
12. [Generate E-Way Bill](#12-generate-e-way-bill)
13. [Consolidated E-Way Bill](#13-consolidated-e-way-bill)
14. [Transporter Update (Assign Transporter)](#14-transporter-update-assign-transporter)
15. [Transporter Update + PDF (2-call flow)](#15-transporter-update--pdf-2-call-flow)
16. [Extend E-Way Bill Validity](#16-extend-e-way-bill-validity)
17. [Self-Transfer Explained](#17-self-transfer-explained)
18. [NIC Error Handling Pattern](#18-nic-error-handling-pattern)
19. [Server-Side Middleware & Token Guard](#19-server-side-middleware--token-guard)

---

## 1. What is Masters India?

[Masters India](https://prod-api.mastersindia.co) is a GSP (GST Suvidha Provider) — a government-authorised intermediary between your application and the NIC (National Informatics Centre) e-way bill portal.

Instead of integrating directly with `ewaybillgst.gov.in` (which requires a separate NIC API account per GSTIN), Masters India provides a single REST API that:

- Proxies all NIC operations (generate, fetch, update, extend, consolidate)
- Handles session management with NIC internally
- Returns structured JSON (NIC returns raw XML/custom formats)
- Wraps NIC errors inside HTTP 200 responses (important — see §18)

**Base URL:** `https://prod-api.mastersindia.co/api/v1/`

---

## 2. Credentials — ID & Password

Stored in `auth/auth_service.py`:

```
Username : eklavyasingh9870@gmail.com
Password : 3Mw@esRcnk3DM@C
Auth URL : https://prod-api.mastersindia.co/api/v1/token-auth/
```

These are the **Masters India account credentials**, not the GST portal login. One set of credentials works for all GSTINs registered under that Masters India account.

The login call is a simple `POST` with JSON body:

```json
POST https://prod-api.mastersindia.co/api/v1/token-auth/
Content-Type: application/json

{
  "username": "eklavyasingh9870@gmail.com",
  "password": "3Mw@esRcnk3DM@C"
}
```

**Response:**
```json
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

---

## 3. Authentication & JWT Token

Masters India uses **JWT (JSON Web Token)** authentication. After login, every subsequent request must carry the token in the `Authorization` header:

```
Authorization: JWT eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

**Token lifetime:** ~24 hours (decoded from the JWT `exp` claim).

The server keeps the token alive across requests through a two-layer cache:

| Layer | Where | Lifetime |
|---|---|---|
| In-memory dict `_token_cache` | `auth_service.py` module-level variable | Survives until process restart |
| File `auth/jwt_token.json` | Disk (may fail on ephemeral filesystems like Docker overlay) | Survives process restart |

On startup the `lifespan` handler in `app.py` calls `load_jwt_token()`, which:
1. Checks `_token_cache["token"]` — if valid, use it
2. Falls back to reading `jwt_token.json` — decodes and validates the `exp` claim
3. If expired or missing, calls `get_jwt_token()` to re-authenticate and refresh both layers

---

## 4. Token File — How It Looks

`auth/jwt_token.json`:

```json
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjozMjM4MywidXNlcm5hbWUiOiJla...",
  "timestamp": "2026-04-28T15:51:22.641151",
  "expires_at": "2026-04-29T15:51:23",
  "username": "eklavyasingh9870@gmail.com",
  "status": "success"
}
```

| Field | Description |
|---|---|
| `token` | The raw JWT string used in the `Authorization` header |
| `timestamp` | When this token was obtained (ISO 8601, local time) |
| `expires_at` | Token expiry extracted from the JWT `exp` claim |
| `username` | Which Masters India account generated this token |
| `status` | Always `"success"` — only written on successful auth |

**JWT Payload (decoded):**
The token is standard JWT: `header.payload.signature`. The payload contains:

```json
{
  "user_id": 32383,
  "username": "eklavyasingh9870@gmail.com",
  "exp": 1777458083,
  "email": "eklavyasingh9870@gmail.com",
  "orig_iat": 1777371683
}
```

`exp` is a Unix timestamp. The code decodes this using `base64.urlsafe_b64decode` — no JWT library needed.

---

## 5. Token Validation Flow

```
Request comes in
      │
      ▼
load_jwt_token()
      │
      ├─ _token_cache["token"] present?
      │      └─ Yes → is_token_valid()
      │               ├─ decode JWT exp claim
      │               ├─ compare with now + 5-minute buffer
      │               └─ Valid? Return token ✅
      │
      ├─ No / Expired → read jwt_token.json
      │      └─ File exists? → is_token_valid()
      │               ├─ Valid? Update cache, return token ✅
      │               └─ Expired? → get_jwt_token() → refresh
      │
      └─ File missing → get_jwt_token() → POST /token-auth/ → save both layers
```

**5-minute buffer:** The check is `now >= (expiry - 5 minutes)`, so tokens are refreshed slightly before actual expiry to avoid mid-request failures.

---

## 6. Request Header Structure

Every Masters India API call uses these headers:

```python
{
    "Authorization": "JWT eyJ0eXAiOiJKV1Qi...",
    "Content-Type": "application/json"
}
```

Two helper functions in `auth_service.py` build this:

- `load_jwt_token()` — returns the raw token string
- `get_auth_headers()` — returns the full headers dict ready to pass to `requests`

---

## 7. API Endpoint Map

| Our Route | Method | Masters India Upstream | Purpose |
|---|---|---|---|
| `/api/ewaybill` | GET | `getEwayBillData/?action=GetEwayBill` | Fetch EWB details |
| `/api/gstin-details` | GET | `getEwayBillData/?action=GetGSTINDetails` | Validate & look up GSTIN |
| `/api/transporter-details` | GET | `getEwayBillData/?action=GetGSTINDetails` | Look up transporter |
| `/api/distance` | GET | `distance/` | Pincode-to-pincode km |
| `/api/generate-ewaybill` | POST | `ewayBillsGenerate/` | Create new EWB |
| `/api/consolidated-ewaybill` | POST | `consolidatedEwayBillsGenerate/` | Merge multiple EWBs |
| `/api/transporter-update` | POST | `transporterIdUpdate/` | Assign transporter to EWB |
| `/api/transporter-update-with-pdf` | POST | `transporterIdUpdate/` × 2 | Assign + fetch PDF |
| `/api/extend-ewaybill` | POST | `ewayBillValidityExtend/` | Extend EWB validity |
| `/api/refresh-token` | POST | `token-auth/` | Force token refresh |

---

## 8. Fetch E-Way Bill Details

**Our endpoint:** `GET /api/ewaybill?eway_bill_number=XXX&gstin=YYY`

**Upstream call:**
```
GET https://prod-api.mastersindia.co/api/v1/getEwayBillData/
    ?action=GetEwayBill
    &gstin=09COVPS5556J1ZT (Company-GSTIN)
    &eway_bill_number=321012345678
```
from tenant_company table we have gstin in it, from that we have to use this gstin in each api

The `gstin` parameter is the **user's own GSTIN** (who is querying), not necessarily the EWB generator's GSTIN. Masters India validates that the querying GSTIN is authorised to view that EWB.

**Successful response shape:**
```json
{
  "status": "success",
  "message": "E-Way Bill details retrieved successfully",
  "data": {
    "results": {
      "status": "OK",
      "code": 200,
      "message": {
        "ewayBillNo": "321012345678",
        "ewayBillDate": "01/05/2026 10:30:00",
        "validUpto": "02/05/2026 23:59:00",
        "generatedBy": "09COVPS5556J1ZT",
        "fromGstin": "09COVPS5556J1ZT",
        "toGstin": "27AABCU9603R1ZX",
        "transporterId": "29AAKCS1741N1ZK",
        "vehicleNo": "UP32AB1234",
        "status": "ACTIVE",
        ...
      }
    }
  }
}
```

---

## 9. GSTIN Validator

**Our endpoint:** `GET /api/gstin-details?userGstin=XXX&gstin=YYY`

Both `gstin-details` and `transporter-details` endpoints call the **same** upstream action `GetGSTINDetails` — they differ only in the label returned to the caller.

**Upstream call:**
```
GET https://prod-api.mastersindia.co/api/v1/getEwayBillData/
    ?action=GetGSTINDetails
    &userGstin=09COVPS5556J1ZT
    &gstin=27AABCU9603R1ZX
```

**What it validates:**
- GSTIN format (15-char regex: `^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$`)
- Whether the GSTIN is **active** on the GST portal (live NIC lookup)
- Returns trade name, legal name, address, state, pincode

**Successful flat response:**
```json
{
  "status": "success",
  "gstin_of_taxpayer": "27AABCU9603R1ZX",
  "trade_name": "ACME LOGISTICS",
  "legal_name_of_business": "ACME LOGISTICS PRIVATE LIMITED",
  "address1": "123 INDUSTRIAL AREA",
  "address2": "ANDHERI EAST",
  "state_name": "Maharashtra",
  "pincode": "400069",
  "taxpayer_type": "Regular",
  "taxpayer_status": "ACT",
  "block_status": "U"
}
```

`block_status: "U"` = Unblocked (can generate EWBs). `"B"` = Blocked.

**Local pre-validation (in `generate_ewaybill_service.py`):**
Before calling Masters India, the generate-ewaybill service validates GSTIN format locally:
```python
GSTIN_REGEX = re.compile(
    r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'
)
```
This catches formatting errors before wasting an API call.

---

## 10. Transporter Details Lookup

**Our endpoint:** `GET /api/transporter-details?userGstin=XXX&gstin=YYY`

Identical upstream call to GSTIN details. Used specifically to pre-fill the transporter name when the user types a transporter GSTIN on the frontend. The response is structured identically to the GSTIN details response.

---

## 11. Distance Between Pincodes

**Our endpoint:** `GET /api/distance?fromPincode=208001&toPincode=400001`

**Upstream call:**
```
GET https://prod-api.mastersindia.co/api/v1/distance/
    ?fromPincode=208001&toPincode=400001
```

**Validation before calling upstream:**
- Both pincodes must be exactly 6 digits (`isdigit()` + `len == 6`)

**Response:**
```json
{
  "status": "success",
  "distance": 1370,
  "from_pincode": "208001",
  "to_pincode": "400001"
}
```

Used to auto-fill `transportation_distance` when generating an EWB.

---

## 12. Generate E-Way Bill

**Our endpoint:** `POST /api/generate-ewaybill`

**Upstream call:**
```
POST https://prod-api.mastersindia.co/api/v1/ewayBillsGenerate/
```

This is the most complex call. The server performs extensive **server-side validation** before hitting Masters India:

### Required Top-Level Fields

| Field | Type | Notes |
|---|---|---|
| `userGstin` | string | Your registered GSTIN (15-char) |
| `supply_type` | string | `"outward"` or `"inward"` |
| `sub_supply_type` | string | e.g. `"Supply"`, `"Import"`, `"Export"` |
| `document_type` | string | See valid types below |
| `document_number` | string | Max 16 chars, alphanumeric + `/` `-` only |
| `document_date` | string | Format `DD/MM/YYYY` |
| `gstin_of_consignor` | string | 15-char GSTIN or `"URP"` (unregistered) |
| `gstin_of_consignee` | string | 15-char GSTIN or `"URP"` |
| `pincode_of_consignor` | string | 6-digit pincode |
| `state_of_consignor` | string | State name |
| `pincode_of_consignee` | string | 6-digit pincode |
| `state_of_supply` | string | Destination state |
| `taxable_amount` | number | |
| `total_invoice_value` | number | Must be >= sum of all tax components |
| `transportation_mode` | string | `"Road"`, `"Rail"`, `"Air"`, `"Ship"`, `"In Transit"` |
| `transportation_distance` | number | 0–4000 km |
| `itemList` | array | 1–250 items |

**Valid document types:**
`Tax Invoice`, `Bill of Supply`, `Bill of Entry`, `Delivery Challan`, `Credit Note`, `Others`

### Required Per Item in `itemList`

| Field | Notes |
|---|---|
| `product_name` | Auto-filled from `product_description` if blank |
| `hsn_code` | 4–8 numeric digits |
| `quantity` | Must be > 0 |
| `unit_of_product` | e.g. `NOS`, `KGS` |
| `taxable_amount` | |
| `cgst_rate` | Negative values auto-corrected to 0 |
| `sgst_rate` | Negative values auto-corrected to 0 |
| `igst_rate` | Negative values auto-corrected to 0 |

### Amount Validation Rule

```
taxable + cgst + sgst + igst + cess + other + cessNonAdvol ≤ total_invoice_value + ₹2 (grace)
```

### Road-specific Rules
- `vehicle_number` required; must match regex `^[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{4}$` or temp format `^TM[A-Z0-9]{6}$`
- `vehicle_type`: `"Regular"` (default) or `"ODC"` (over-dimensional cargo)

### Rail/Air/Ship Rules
- `transporter_document_number` required

### Field Normalisation
The service accepts both snake_case and camelCase from the frontend:
- `user_gstin` → `userGstin`
- `item_list` → `itemList`

**Successful response:**
```json
{
  "status": "success",
  "message": "E-Way Bill generated successfully",
  "eway_bill_number": "321012345678",
  "eway_bill_date": "02/05/2026 10:30:00",
  "valid_upto": "03/05/2026 23:59:00",
  "data": { ... }
}
```

---

## 13. Consolidated E-Way Bill

**Our endpoint:** `POST /api/consolidated-ewaybill`

**Upstream call:**
```
POST https://prod-api.mastersindia.co/api/v1/consolidatedEwayBillsGenerate/
```

Used when a single vehicle carries goods covered by **multiple individual E-Way Bills**. Instead of presenting each EWB separately, a Consolidated EWB (CEWB) is generated that references all of them.

### Required Fields

| Field | Type | Notes |
|---|---|---|
| `userGstin` | string | Your GSTIN |
| `place_of_consignor` | string | Dispatch location |
| `state_of_consignor` | string | |
| `vehicle_number` | string | Vehicle carrying all consignments |
| `mode_of_transport` | string | `"Road"`, `"Rail"`, etc. |
| `transporter_document_number` | string | LR/RR number |
| `transporter_document_date` | string | `DD/MM/YYYY` |
| `data_source` | string | Usually `"E"` (e-way bill system) |
| `list_of_eway_bills` | array | List of EWB numbers to consolidate |

### Smart Format Handling

The service auto-transforms `list_of_eway_bills` if passed as a flat array of strings:

```json
// You can send either format:
"list_of_eway_bills": ["321012345678", "321012345679"]

// Or:
"list_of_eway_bills": [
  {"eway_bill_number": "321012345678"},
  {"eway_bill_number": "321012345679"}
]
```

Both are accepted. The flat string array is auto-converted to the object format that the Masters India API expects.

**Successful response:**
```json
{
  "status": "success",
  "message": "Consolidated E-Way Bill created successfully",
  "cEwbNo": "3401234567",
  "cEwbDate": "02/05/2026 11:00:00",
  "url": "https://ewaybillgst.gov.in/BillPrint/...pdf"
}
```

---

## 14. Transporter Update (Assign Transporter)

**Our endpoint:** `POST /api/transporter-update`

**Upstream call:**
```
POST https://prod-api.mastersindia.co/api/v1/transporterIdUpdate/
```

Used when the **generator** of the EWB needs to assign or change the transporter. This happens when:
- The EWB was generated without a transporter (Part-B blank)
- The transporter changed mid-journey

### Request Body

```json
{
  "userGstin": "09COVPS5556J1ZT",
  "eway_bill_number": 321012345678,
  "transporter_id": "29AAKCS1741N1ZK",
  "transporter_name": "FAST MOVERS PVT LTD"
}
```

Note: `eway_bill_number` is coerced to `int` before sending to Masters India.

### NIC Error Codes (common)

| Code | Meaning |
|---|---|
| `338` | You are not authorised to update transporter details (wrong GSTIN) |
| `312` | E-Way Bill already cancelled |
| `340` | E-Way Bill has expired |

**Successful response:**
```json
{
  "status": "success",
  "message": "Transporter ID updated successfully",
  "eway_bill_number": 321012345678,
  "transporter_id": "29AAKCS1741N1ZK",
  "update_date": "02/05/2026 12:00:00",
  "pdf_url": "https://ewaybillgst.gov.in/BillPrint/..."
}
```

---

## 15. Transporter Update + PDF (2-call flow)

**Our endpoint:** `POST /api/transporter-update-with-pdf`

Makes **two sequential POST calls** to `transporterIdUpdate/` with the same payload.

**Why two calls?**
According to Masters India's own support: the first call performs the update on the NIC server; the second call (immediately after) fetches the updated PDF with Part-B filled in. The PDF is not always available in the first response.

**Flow:**
```
POST transporterIdUpdate/  →  Update applied at NIC
         │
         ▼
POST transporterIdUpdate/  →  Fetch PDF (base64 in response or URL)
         │
         ▼
Return both responses to caller
```

**Check logic for PDF:**
```python
if "pdf" in str(response2_data).lower() or "base64" in str(response2_data).lower():
    # PDF data found
```

---

## 16. Extend E-Way Bill Validity

**Our endpoint:** `POST /api/extend-ewaybill`

**Upstream call:**
```
POST https://prod-api.mastersindia.co/api/v1/ewayBillValidityExtend/
```

### Business Rules (enforced server-side)

| Transport Mode | Code | `consignment_status` | `transit_type` |
|---|---|---|---|
| Road | 1 | `"M"` (Moving) | `""` (blank) |
| Rail | 2 | `"M"` | `""` |
| Air | 3 | `"M"` | `""` |
| Ship | 4 | `"M"` | `""` |
| In Transit | 5 | `"T"` (In Transit) | `"R"`, `"W"`, or `"O"` |

Transit types for mode 5:
- `"R"` = Road
- `"W"` = Warehouse
- `"O"` = Others

### Required Fields

```json
{
  "userGstin": "09COVPS5556J1ZT",
  "eway_bill_number": 321012345678,
  "vehicle_number": "UP32AB1234",
  "place_of_consignor": "Kanpur",
  "state_of_consignor": "Uttar Pradesh",
  "remaining_distance": 250,
  "mode_of_transport": "1",
  "extend_validity_reason": "Natural Calamity",
  "extend_remarks": "Road blocked due to floods",
  "consignment_status": "M",
  "transit_type": "",
  "from_pincode": 208001,
  "address_line1": "123 Naubasta",
  "address_line2": "Kanpur",
  "address_line3": "UP"
}
```

### Constraints (from NIC rules)
- Extension can only be requested **between 8 hours before and 8 hours after expiry**
- Only the **current transporter** can extend (or the generator if no transporter assigned)
- `remaining_distance` must not exceed the original distance on the EWB

---

## 17. Self-Transfer Explained

A **self-transfer** is when the **same GSTIN appears as both consignor and consignee** in the generate-ewaybill payload. This is used for:

- **Stock transfer** between two branches of the same business (same GSTIN, different addresses)
- **Job work** returns
- **Own warehouse** transfers

To generate a self-transfer EWB, use the generate endpoint with:

```json
{
  "supply_type": "outward",
  "sub_supply_type": "SKD/CKD",
  "document_type": "Delivery Challan",
  "gstin_of_consignor": "09COVPS5556J1ZT",
  "gstin_of_consignee": "09COVPS5556J1ZT",
  "state_of_consignor": "Uttar Pradesh",
  "state_of_supply": "Maharashtra",
  ...
}
```

Since both GSTINs are the same, Masters India / NIC recognises this as a self-transfer and allows it without requiring a separate consignee registration. This is a standard NIC feature — no special API is needed.

---

## 18. NIC Error Handling Pattern

Masters India wraps NIC errors inside **HTTP 200 responses**. A successful HTTP status does not mean the operation succeeded. The code always inspects the nested `results` object:

```python
results = response.json().get("results", {})
code    = results.get("code", 200)    # 204 = NIC error
status  = results.get("status", "")  # "No Content" = NIC error
message = results.get("message", {}) # error string or success dict
```

**Error detection logic:**

```python
if code == 204 or status == "No Content":
    # NIC returned an error
    raw_error = message  # e.g. "338: You cannot update transporter details..."
```

NIC errors come as strings like `"338: You cannot update transporter details for this EWB"`. The code parses these with:

```python
match = re.match(r'^(\d+):\s*(.+)$', error_message.strip())
nic_code        = match.group(1)   # "338"
nic_description = match.group(2)   # "You cannot update..."
```

The parsed error is returned as `error_code` + `error_description` for the frontend to display cleanly.

---

## 19. Server-Side Middleware & Token Guard

`app.py` has an HTTP middleware `ensure_valid_token` that runs on **every request** to e-way bill routes:

```python
SKIP_AUTH_PATHS = {"/api/health", "/api/refresh-token", "/docs", "/openapi.json", "/redoc"}

async def ensure_valid_token(request, call_next):
    path = request.url.path
    # Skip bilty, challan, and utility routes
    if path in SKIP_AUTH_PATHS or path.startswith("/api/bilty") or path.startswith("/api/challan"):
        return await call_next(request)

    # For all ewaybill routes: ensure token is valid
    token = load_jwt_token()
    if not token:
        token = get_jwt_token()   # auto-refresh
        if not token:
            return 401 Unauthorized
    
    return await call_next(request)
```

This means the token is **proactively validated and refreshed** before the request ever reaches the service handler. Individual services also call `load_jwt_token()` themselves as a second safety net.

**Force refresh endpoint:**
```
POST /api/refresh-token
```
No body required. Calls `get_jwt_token()` directly, bypassing cache validation. Use this if the token is suspected corrupt.
