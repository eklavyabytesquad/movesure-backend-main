# E-Way Bill (EWB) Services

Integration with the **Masters India GSP API** for E-Way Bill generation, validation, transporter assignment, and validity extension.  Every mutating operation is persisted to the database.

---

## Module Structure

```
app/services/ewaybill/
├── __init__.py            Re-exports public API
├── token_service.py       Masters India JWT manager (3-layer cache)
├── exceptions.py          EWayBillError + NIC error parser
├── validators.py          GSTIN / vehicle / payload validators
├── nic_client.py          HTTP helpers (nic_get, nic_post)
├── db.py                  Supabase persistence helpers
├── settings_service.py    Per-company ewb_settings CRUD (GSTIN config)
├── lookup_service.py      GSTIN lookup, transporter lookup, distance (read-only)
├── records_service.py     fetch_ewaybill + DB save
├── generate_service.py    generate_ewaybill + generate_consolidated_ewaybill + DB
├── transporter_service.py update_transporter + update_transporter_with_pdf + DB
├── extend_service.py      extend_ewaybill + DB
└── service.py             Backward-compat shim (re-exports from above)
```

---

## API Endpoints

Base path: `/v1/ewaybill`  
All endpoints (except token endpoints) require a valid `Authorization: Bearer <JWT>` header.

| Method | Path | DB Write | Description |
|--------|------|----------|-------------|
| GET  | `/token/status` | — | Show Masters India JWT status |
| POST | `/token/refresh` | — | Force-refresh Masters India JWT |
| GET  | `/validate` | ✅ | Fetch EWB from NIC + save to DB |
| GET  | `/gstin` | — | GSTIN lookup / validator |
| GET  | `/transporter` | — | Transporter GSTIN lookup |
| GET  | `/distance` | — | Road distance between pincodes |
| POST | `/generate` | ✅ | Generate new EWB + save to DB |
| POST | `/consolidate` | ✅ | Consolidated EWB + save to DB |
| POST | `/transporter-update` | ✅ | Assign / change transporter + save to DB |
| POST | `/transporter-update-pdf` | ✅ | Transporter update + fetch PDF + save to DB |
| POST | `/extend` | ✅ | Extend EWB validity + save to DB |
| GET  | `/settings` | — | Get company EWB settings (GSTIN etc.) |
| POST | `/settings` | ✅ | Create / update company EWB settings |
| DELETE | `/settings` | ✅ | Deactivate company EWB settings |

> **Masters India account is locked** to `eklavyasingh9870@gmail.com` across all companies.  
> **The frontend never passes `userGstin` or credentials.** The backend reads the company GSTIN from `ewb_settings` automatically using the `company_id` in the auth token.

---

## One-Time Setup (Required)

Before any EWB operation, the company admin must save the company GSTIN once:

```
POST /v1/ewaybill/settings
{ "company_gstin": "07AAACR5055K1Z5" }
```

After that, **all EWB endpoints work without any GSTIN in the request** — it is always resolved server-side from the stored settings.

---

## Endpoint Details

### `GET /validate`
Fetch full EWB details and snapshot them in the DB.  
The company GSTIN is resolved automatically from settings.

Query params:
- `eway_bill_number` — 12-digit EWB number
- `bilty_id` *(optional)* — UUID of the related bilty to link

DB writes: `ewb_records` (upsert) → `ewb_validation_log` (version++) → `ewb_events` (`VALIDATED`)

---

### `GET /gstin`
Validate and look up any GSTIN.  Your company GSTIN is resolved from settings automatically.

Query params:
- `gstin` — GSTIN to look up

---

### `GET /transporter`
Look up a transporter GSTIN.  Your company GSTIN is resolved from settings automatically.

Query params:
- `gstin` — Transporter GSTIN to look up

---

### `POST /generate`
Generate a new EWB on NIC and persist.  **Do not send `userGstin`** — it is injected from settings.

Required body fields:
```json
{
  "supply_type": "O",
  "sub_supply_type": "1",
  "document_type": "Tax Invoice",
  "document_number": "INV/2024/001",
  "document_date": "01/01/2025",
  "gstin_of_consignor": "07AAACR5055K1Z5",
  "gstin_of_consignee": "27AAACR5055K1Z5",
  "pincode_of_consignor": "110001",
  "state_of_consignor": "07",
  "pincode_of_consignee": "400001",
  "state_of_supply": "27",
  "taxable_amount": 10000,
  "total_invoice_value": 11800,
  "transportation_mode": "Road",
  "transportation_distance": 1500,
  "itemList": [
    {
      "product_name": "Goods",
      "hsn_code": "8471",
      "quantity": 1,
      "unit": "NOS",
      "taxable_value": 10000,
      "cgst_rate": 9,
      "sgst_rate": 9,
      "igst_rate": 0
    }
  ],
  "vehicle_number": "UP32AB1234",
  "bilty_id": "uuid-of-bilty"
}
```

DB writes: `ewb_records` (insert) → `ewb_validation_log` (v1) → `ewb_events` (`GENERATED`)

---

### `POST /consolidate`
Create a Consolidated EWB for multiple individual EWBs on one vehicle.  **Do not send `userGstin`.**

```json
{
  "place_of_consignor": "New Delhi",
  "state_of_consignor": "07",
  "vehicle_number": "UP32AB1234",
  "mode_of_transport": "1",
  "transporter_document_number": "TR123",
  "transporter_document_date": "01/01/2025",
  "data_source": "E",
  "list_of_eway_bills": ["321012345678", "321012345679"]
}
```

DB writes: `ewb_consolidated` (insert) → `ewb_events` (`CONSOLIDATED`) → `ewb_records.cewb_id` updated on all member EWBs

---

### `POST /transporter-update`
Assign or change the transporter on an existing EWB.  **Do not send `userGstin`.**

```json
{
  "eway_bill_number": 321012345678,
  "transporter_id": "29AABCU9603R1ZX",
  "transporter_name": "Fast Carriers Pvt Ltd"
}
```

DB writes: `ewb_records` (patch transporter fields) → `ewb_events` (`TRANSPORTER_UPDATED`)

---

### `POST /transporter-update-pdf`
Same as above but makes a second NIC call to retrieve the updated PDF (Part-B filled).

DB writes: same as `/transporter-update` but event type is `TRANSPORTER_PDF`

---

### `POST /extend`
Extend the validity of an expiring EWB.  NIC allows extension 8 hours before to 8 hours after expiry.  **Do not send `userGstin`.**

```json
{
  "eway_bill_number": 321012345678,
  "vehicle_number": "UP32AB1234",
  "place_of_consignor": "New Delhi",
  "state_of_consignor": "07",
  "remaining_distance": 200,
  "mode_of_transport": "1",
  "extend_validity_reason": "Natural Calamity",
  "from_pincode": 110001
}
```

`mode_of_transport` codes: `1`=Road `2`=Rail `3`=Air `4`=Ship `5`=In Transit  
`transit_type` (mode 5 only): `R`=Road `W`=Warehouse `O`=Others

DB writes: `ewb_records` (status=`EXTENDED`, new `valid_upto`) → `ewb_validation_log` (version++) → `ewb_events` (`EXTENDED`)

---

## Company EWB Settings

Before using any EWB API, each company **must** configure its GSTIN via the settings endpoint.
The GSTIN is stored once and reused on every NIC call — users never have to pass `userGstin` manually after setup.

### `GET /settings`
Returns the current EWB configuration for the caller's company.

Response:
```json
{
  "status": "success",
  "mi_account": "eklavyasingh9870@gmail.com",
  "data": {
    "settings_id": "uuid",
    "company_id": "uuid",
    "company_gstin": "07AAACR5055K1Z5",
    "mi_username": "eklavyasingh9870@gmail.com",
    "auto_attach_bilty": false,
    "is_active": true,
    "metadata": {}
  }
}
```

Returns **404** if settings have not been configured yet.

---

### `POST /settings`
Create or update EWB settings for the company.  **Only `company_gstin` is required.**

Request body:
```json
{
  "company_gstin": "07AAACR5055K1Z5"
}
```

The `mi_username` (Masters India account) is **always forced** to `eklavyasingh9870@gmail.com` — it cannot be overridden via the API.

> **Frontend note:** Send only `company_gstin`. No other fields are needed. The backend handles defaults for all other columns.

Response:
```json
{
  "status": "success",
  "message": "EWB settings saved successfully.",
  "mi_account": "eklavyasingh9870@gmail.com",
  "data": { ... }
}
```

---

### `DELETE /settings`
Soft-deactivates the company's EWB settings (`is_active = false`).  The row is preserved for audit.

---

## Database Schema

### `ewb_records`
Primary store for each EWB.  One row per (company_id, eway_bill_number).

Key columns: `eway_bill_number`, `ewb_status`, `ewb_date`, `valid_upto`, `bilty_id`, `cewb_id`, `items_json` (JSONB), `raw_response` (JSONB), `transporter_id`, `vehicle_number`

**`ewb_status` values:** `ACTIVE` | `CANCELLED` | `EXTENDED` | `EXPIRED` | `PART_DELIVERED` | `CONSOLIDATED`

### `ewb_validation_log`
Versioned NIC snapshots.  Appended on every fetch/generate/extend.

Key columns: `ewb_id` (FK), `version_no` (auto-incremented by app), `nic_snapshot` (JSONB), `triggered_by` (`FETCH`/`GENERATE`/`EXTEND`)

### `ewb_events`
Immutable event log.  INSERT-only — rows are never updated.

Key columns: `ewb_id` (FK), `event_type`, `event_data` (JSONB), `raw_response` (JSONB)

**`event_type` values:** `GENERATED` | `CANCELLED` | `VALIDATED` | `TRANSPORTER_UPDATED` | `TRANSPORTER_PDF` | `EXTENDED` | `CONSOLIDATED` | `PART_B_UPDATED` | `FETCHED` | `EXPIRED`

### `ewb_consolidated`
One row per Consolidated EWB.

Key columns: `cewb_number`, `ewb_numbers` (JSONB array of member EWB numbers), `pdf_url`, `raw_response`

---

### `ewb_settings`
One row per company.  Stores the company GSTIN and the locked Masters India account.

Key columns: `company_gstin` (GSTIN used on all NIC calls), `mi_username` (always `eklavyasingh9870@gmail.com`)

> **Note:** Columns `auto_attach_bilty`, `is_active`, `metadata` are defined in the schema but require the full `012_ewaybill_module.sql` migration to be applied.  The API only writes `company_gstin` + `mi_username` so it works even on a partial migration.

---

## Token Management

Masters India uses a 24-hour JWT.  `token_service.py` implements a 3-layer cache:

1. **Memory** — fastest, lost on process restart  
2. **Disk** — `jwt_token.json` next to the module, survives restarts  
3. **Live fetch** — POSTs to Masters India `/token-auth/` when both caches are stale  

A 5-minute early-refresh buffer prevents using a token in its last 5 minutes.

```
GET /v1/ewaybill/token/status   -- check token (no refresh)
POST /v1/ewaybill/token/refresh -- force new token
```

---

## Error Handling

| Exception | HTTP code | When |
|-----------|-----------|------|
| `EWayBillError` | 422 | NIC returned a business error (HTTP 200 but `code=204`) |
| `ValueError` | 400 | Input validation failed before calling NIC |
| Any other | 502 | Unexpected upstream / network error |

NIC error codes follow the pattern `"338: Not authorised to generate EWB"`.  The router exposes `nic_code` and `error` in the response detail.

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `MI_USERNAME` | Masters India login email |
| `MI_PASSWORD` | Masters India login password |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anon/service key |
| `JWT_SECRET` | App JWT secret (for user auth) |

---

## NIC Error Patterns to Know

| NIC Code | Meaning |
|----------|---------|
| 338 | Not authorised / GSTIN mismatch |
| 312 | EWB already cancelled |
| 322 | Outside extension window |
| 121 | Invalid vehicle number format |
| 204 | Generic "No Content" error envelope |
