# Fleet Services — API Reference

## Overview

The Fleet module provides a structured registry for **vehicles** (`fleet`) and
**fleet staff** (`fleet_staff`) — drivers, owners, conductors, and mechanics.

### Why Fleet?

Previously, challans and trip sheets stored vehicle + driver info as free-form
JSONB (`vehicle_info`).  This caused:
- No validation — any text could be entered as a vehicle number
- No document expiry tracking — insurance, RC, permits would lapse silently
- No reuse — same driver had to be typed again on every challan
- No history — no way to see all challans for a specific vehicle

The Fleet module replaces that with **FK-linked records** so every challan and
trip sheet points to an actual registered vehicle and real staff people.

---

## Object Hierarchy

```
tenant_companies
└── fleet                  (vehicles)
    ├── current_driver_id  → fleet_staff
    ├── current_owner_id   → fleet_staff
    └── current_conductor_id → fleet_staff

challan
├── fleet_id               → fleet
├── driver_id              → fleet_staff
├── owner_id               → fleet_staff
└── conductor_id           → fleet_staff

challan_trip_sheet
├── fleet_id               → fleet
├── driver_id              → fleet_staff
├── owner_id               → fleet_staff
└── conductor_id           → fleet_staff
```

> **`vehicle_info` JSONB is retained** on challan and trip_sheet as a
> snapshot/override for legacy data or extra fields not covered by the schema.

---

## Fleet Staff

A **fleet staff** record represents one person: an owner, driver, conductor,
cleaner, or mechanic.  Staff are company-scoped and can be reused across
multiple challans.

### Role Types

| Role | Description |
|------|-------------|
| `OWNER` | Vehicle owner or transport contractor. Usually appears as the payee for freight settlements. |
| `DRIVER` | Primary truck driver. Fill `license_no`, `license_expiry`, `license_type` for compliance. |
| `CONDUCTOR` | Helper/assistant who travels with the driver. |
| `CLEANER` | Yard-based vehicle cleaner. |
| `MECHANIC` | In-house mechanic for fleet maintenance. |

---

### `POST /v1/fleet/staff` — Create Fleet Staff

Register a new staff member.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Full name |
| `role` | string | ✅ | `OWNER` / `DRIVER` / `CONDUCTOR` / `CLEANER` / `MECHANIC` |
| `branch_id` | UUID | — | Branch affiliation (null = company-wide) |
| `mobile` | string | — | Primary mobile (10–15 digits) |
| `alternate_mobile` | string | — | Alternate mobile |
| `email` | string | — | Email address |
| `address` | text | — | Residential address |
| `aadhar_no` | string | — | 12-digit Aadhaar number |
| `pan_no` | string | — | 10-char PAN number |
| `license_no` | string | — | Driving licence number (for DRIVER role) |
| `license_expiry` | date (YYYY-MM-DD) | — | Licence expiry — tracked for alerts |
| `license_type` | string | — | `LMV` / `HMV` / `BOTH` |
| `badge_no` | string | — | Employee / badge ID |
| `date_of_birth` | date | — | Date of birth |
| `date_of_joining` | date | — | Joining date |
| `emergency_contact_name` | string | — | Emergency contact name |
| `emergency_contact_mobile` | string | — | Emergency contact mobile |
| `bank_account_no` | string | — | Bank account number |
| `bank_ifsc` | string | — | IFSC code |
| `bank_name` | string | — | Bank name |
| `profile_photo_url` | string | — | URL of uploaded photo |
| `notes` | text | — | Internal notes |
| `metadata` | object | — | Extra key-value fields |

**Example:**
```json
{
  "name": "Ramesh Kumar",
  "role": "DRIVER",
  "mobile": "9876543210",
  "license_no": "MH0120191234567",
  "license_expiry": "2027-03-15",
  "license_type": "HMV",
  "aadhar_no": "123456789012"
}
```

**Response:** Created `fleet_staff` record.

---

### `GET /v1/fleet/staff` — List Fleet Staff

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `role` | string | Filter by role: `OWNER` / `DRIVER` / `CONDUCTOR` / `CLEANER` / `MECHANIC` |
| `branch_id` | UUID | Filter by branch |
| `is_active` | boolean | Default `true`. Pass `false` to list deactivated staff. |
| `search` | string | Partial name match (case-insensitive) |
| `limit` | int | Max results (default 50) |
| `offset` | int | Pagination offset (default 0) |

**Example:** `GET /v1/fleet/staff?role=DRIVER&is_active=true`

---

### `GET /v1/fleet/staff/{staff_id}` — Get Fleet Staff Detail

Returns full profile of one staff member including all document fields.

---

### `PATCH /v1/fleet/staff/{staff_id}` — Update Fleet Staff

Partial update — only supplied fields are changed.

**Tip:** To deactivate a staff member without losing history, set `is_active: false`
instead of deleting.

---

### `DELETE /v1/fleet/staff/{staff_id}` — Deactivate Fleet Staff

Soft-delete: sets `is_active = false`.  Existing challan records that
reference this staff are **not affected**.

---

## Fleet (Vehicles)

A **fleet** record is one physical vehicle.  Tracks all statutory documents
with expiry dates.

### Vehicle Type Values

| Value | Description |
|-------|-------------|
| `TRUCK` | Standard goods truck (e.g. Tata 407, Ashok Leyland 1109) |
| `TRAILER` | Semi-trailer or full trailer |
| `MINI_TRUCK` | Small commercial vehicle (e.g. Tata Ace, Mahindra Bolero Pickup) |
| `PICKUP` | Pickup van |
| `TANKER` | Liquid / gas tanker |
| `OTHER` | Any other vehicle type |

### Body Type Values

| Value | Description |
|-------|-------------|
| `OPEN` | Open truck body |
| `CLOSED` | Closed / covered body |
| `CONTAINER` | Container body |
| `FLATBED` | Flatbed / platform trailer |
| `TANKER` | Tanker body |
| `OTHER` | Other body type |

### Fleet Status Values

| Status | Description |
|--------|-------------|
| `ACTIVE` | Available and road-worthy |
| `IN_TRANSIT` | Currently on a trip |
| `MAINTENANCE` | Under repair or scheduled service |
| `INACTIVE` | Retired, sold, or permanently grounded |

---

### `POST /v1/fleet` — Register a Fleet Vehicle

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `vehicle_no` | string | ✅ | Registration number (e.g. `MH04AB1234`). Unique per company. |
| `vehicle_type` | string | — | Default `TRUCK`. See types above. |
| `branch_id` | UUID | — | Primary branch (null = company-wide) |
| `make` | string | — | Manufacturer (e.g. `TATA`, `ASHOK LEYLAND`) |
| `model` | string | — | Model name (e.g. `407`, `Prima 4028`) |
| `year_of_manufacture` | integer | — | Year (e.g. `2019`) |
| `body_type` | string | — | `OPEN` / `CLOSED` / `CONTAINER` / `FLATBED` / `TANKER` / `OTHER` |
| `capacity_kg` | number | — | Load capacity in kg (e.g. `10000` for 10 tons) |
| `color` | string | — | Vehicle colour |
| `engine_no` | string | — | Engine number from RC |
| `chassis_no` | string | — | Chassis number from RC |
| `rc_no` | string | — | RC (Registration Certificate) number |
| `rc_expiry` | date | — | RC expiry `YYYY-MM-DD` |
| `insurance_no` | string | — | Insurance policy number |
| `insurance_company` | string | — | Insurer name (e.g. `New India Assurance`) |
| `insurance_expiry` | date | — | Insurance expiry `YYYY-MM-DD` ⚠️ critical |
| `permit_no` | string | — | Permit number |
| `permit_type` | string | — | `NATIONAL` / `STATE` / `LOCAL` |
| `permit_expiry` | date | — | Permit expiry `YYYY-MM-DD` |
| `fitness_no` | string | — | Fitness Certificate number |
| `fitness_expiry` | date | — | Fitness expiry `YYYY-MM-DD` |
| `puc_no` | string | — | PUC certificate number |
| `puc_expiry` | date | — | PUC expiry `YYYY-MM-DD` |
| `current_owner_id` | UUID | — | `fleet_staff.staff_id` with `role=OWNER` |
| `current_driver_id` | UUID | — | `fleet_staff.staff_id` with `role=DRIVER` |
| `current_conductor_id` | UUID | — | `fleet_staff.staff_id` with `role=CONDUCTOR` |
| `status` | string | — | Default `ACTIVE` |
| `notes` | text | — | Internal notes |
| `metadata` | object | — | Extra key-value fields |

**Example:**
```json
{
  "vehicle_no": "MH04AB1234",
  "vehicle_type": "TRUCK",
  "make": "TATA",
  "model": "407",
  "year_of_manufacture": 2020,
  "capacity_kg": 4000,
  "rc_no": "MH04AB1234",
  "rc_expiry": "2030-06-30",
  "insurance_no": "POL/2024/12345",
  "insurance_company": "New India Assurance",
  "insurance_expiry": "2025-04-30",
  "permit_type": "NATIONAL",
  "permit_expiry": "2026-01-15",
  "fitness_expiry": "2026-06-30",
  "puc_expiry": "2025-01-31",
  "current_driver_id": "uuid-of-ramesh-kumar",
  "current_owner_id": "uuid-of-owner"
}
```

---

### `GET /v1/fleet` — List Fleet Vehicles

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `branch_id` | UUID | Filter by branch |
| `vehicle_type` | string | `TRUCK` / `TRAILER` / `MINI_TRUCK` / `PICKUP` / `TANKER` / `OTHER` |
| `status` | string | `ACTIVE` / `IN_TRANSIT` / `MAINTENANCE` / `INACTIVE` |
| `is_active` | boolean | Default `true` |
| `search` | string | Partial vehicle number match |
| `limit` | int | Default 50 |
| `offset` | int | Default 0 |

**Response includes embedded staff objects:**
```json
{
  "fleet_id": "...",
  "vehicle_no": "MH04AB1234",
  "current_driver": {
    "staff_id": "...",
    "name": "Ramesh Kumar",
    "mobile": "9876543210",
    "role": "DRIVER"
  },
  "current_owner": { ... },
  "current_conductor": null
}
```

---

### `GET /v1/fleet/{fleet_id}` — Get Fleet Vehicle Detail

Returns full vehicle record with all document fields and embedded staff info
(driver/owner/conductor) including `license_no` and `license_expiry`.

---

### `PATCH /v1/fleet/{fleet_id}` — Update Fleet Vehicle

Partial update — only supplied fields are changed.  All fields from
`POST /v1/fleet` are accepted.

---

### `PATCH /v1/fleet/{fleet_id}/assign` — Assign Staff to Vehicle

Assign or replace the driver / owner / conductor on a vehicle.

| Field | Type | Description |
|-------|------|-------------|
| `owner_id` | UUID or null | `fleet_staff.staff_id` (OWNER role). `null` = no change. `""` = clear. |
| `driver_id` | UUID or null | `fleet_staff.staff_id` (DRIVER role). |
| `conductor_id` | UUID or null | `fleet_staff.staff_id` (CONDUCTOR role). |

**Example — replace only the driver:**
```json
{
  "driver_id": "uuid-of-new-driver"
}
```

**Example — clear conductor:**
```json
{
  "conductor_id": ""
}
```

> ⚠️ Changes here do NOT retroactively update existing challans.
> Challans snapshot staff at creation time.

---

### `DELETE /v1/fleet/{fleet_id}` — Deactivate Fleet Vehicle

Soft-delete: sets `is_active = false` and `status = INACTIVE`.
Existing challans referencing this vehicle are **not affected**.

---

## Integration with Challan

When creating a challan (`POST /v1/challan`) or trip sheet
(`POST /v1/trip-sheet`), supply fleet FKs alongside or instead of
the legacy `vehicle_info` blob:

```json
{
  "challan_date": "2025-01-15",
  "fleet_id": "uuid-of-vehicle",
  "driver_id": "uuid-of-driver",
  "owner_id": "uuid-of-owner",
  "conductor_id": "uuid-of-conductor",
  "vehicle_info": {}
}
```

**Lookup flow for the frontend:**
1. User types or selects vehicle number → call `GET /v1/fleet?search=MH04`
2. User selects a vehicle → auto-fill `fleet_id`, `current_driver_id`, `current_owner_id`
3. User can override individual staff from the fleet_staff dropdown

---

## Document Expiry Tracking

The following dates are indexed for expiry alerts. Your frontend settings
UI should query these and show warnings:

**Vehicle documents:**
- `rc_expiry`
- `insurance_expiry` — ⚠️ critical, expired = cannot operate
- `permit_expiry`
- `fitness_expiry`
- `puc_expiry`

**Staff documents:**
- `license_expiry` — filter drivers with `GET /v1/fleet/staff?role=DRIVER`

**Recommended alert thresholds:**

| Document | Warning | Critical |
|----------|---------|----------|
| Insurance | 30 days | 7 days |
| RC | 60 days | 30 days |
| Permit | 30 days | 14 days |
| Fitness | 30 days | 14 days |
| PUC | 15 days | 7 days |
| Driver licence | 60 days | 30 days |

---

## Settings UI Guide

Recommended pages for a **Fleet Settings** section:

### 1. Fleet Staff List (`/settings/fleet/staff`)
- Table with columns: Name, Role, Mobile, Licence No, Licence Expiry, Status
- Add / Edit / Deactivate buttons
- Filter by Role, Branch, Active status
- Search by name
- Colour-code expired / near-expiry licences

### 2. Fleet Staff Detail / Form (`/settings/fleet/staff/:id`)
- Tabs: **Basic Info** | **Documents** | **Bank Details**
- Basic Info: name, role, mobile, email, address, badge_no, DOB, DOJ
- Documents: Aadhaar, PAN, licence (no/type/expiry), emergency contact
- Bank: account, IFSC, bank name

### 3. Fleet Vehicle List (`/settings/fleet/vehicles`)
- Table: Vehicle No, Type, Make/Model, Driver, Status, Insurance Expiry
- Add / Edit / Deactivate buttons
- Filter by Type, Status, Branch
- Search by vehicle number
- Highlight vehicles with expiring documents (red/orange badges)

### 4. Fleet Vehicle Detail / Form (`/settings/fleet/vehicles/:id`)
- Tabs: **Vehicle Details** | **Documents** | **Assigned Staff**
- Vehicle Details: vehicle_no, type, make, model, year, body_type, capacity, colour, engine_no, chassis_no
- Documents: RC, insurance, permit, fitness, PUC — each with number + expiry date
- Assigned Staff: dropdown search from fleet_staff for owner/driver/conductor
  - Use `GET /v1/fleet/staff?role=DRIVER` to populate driver dropdown
  - Use `GET /v1/fleet/staff?role=OWNER` for owner dropdown

### 5. Expiry Alerts Dashboard (`/settings/fleet/alerts`)
- List all vehicles with any document expiring within 60 days
- List all drivers with licence expiring within 60 days
- Group by: Expired / Critical (< 7 days) / Warning (7–30 days) / Upcoming (30–60 days)

---

## Error Reference

| HTTP | When |
|------|------|
| 404 | fleet or fleet_staff not found (or belongs to different company) |
| 409 | Vehicle number already registered for this company |
| 400 | `PATCH /assign` called with no staff fields supplied |
| 422 | Validation error (invalid role / license_type / vehicle_type value) |
| 500 | Unexpected database error |

---

## Load Order (Schema)

For a fresh database, run schema files in this order:

1. `tenant.sql`
2. `iam.sql`
3. `app.sql`
4. `master.sql`
5. `bilty.sql`
6. `fleet.sql`   ← new
7. `challan.sql` ← references fleet tables

For an existing database, run migration `010_fleet_module.sql`.
