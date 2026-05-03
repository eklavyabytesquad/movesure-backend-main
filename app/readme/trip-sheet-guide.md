# Trip Sheet — Complete Guide

## What is a Trip Sheet?

A Trip Sheet (`challan_trip_sheet`) is a **company-level truck journey record**. It is NOT scoped to a single branch — by design, multiple branches can load their challans onto one physical truck trip.

One truck → one trip sheet → many challans from many branches → many bilties.

### Lifecycle

```
DRAFT → OPEN → DISPATCHED → ARRIVED → CLOSED
```

| Status | Meaning | Who acts |
|---|---|---|
| `DRAFT` | Being built — challans and bilties can be freely added/removed | Creating branch |
| `OPEN` | Truck confirmed, vehicle & driver locked in | Creating branch |
| `DISPATCHED` | Truck physically left the origin | Creating branch |
| `ARRIVED` | Truck reached destination | Receiving branch |
| `CLOSED` | Fully reconciled — kaat settled, deliveries done | Admin |

---

## Trip Sheet Creation — Full Form

The frontend currently asks for very few fields. Below is the **complete form** that should be shown, grouped by section.

### Section 1 — Basic Info (Required)

| Field | Label | Type | Notes |
|---|---|---|---|
| `trip_sheet_no` | Trip Sheet No. | Text | Unique per company; e.g. `TS-001/25` — staff enters this manually |
| `trip_date` | Trip Date | Date picker | Defaults to today |

### Section 2 — Route

| Field | Label | Type | API Source |
|---|---|---|---|
| `from_city_id` | From City | Searchable dropdown | `GET /v1/master/cities` |
| `to_city_id` | To City | Searchable dropdown | `GET /v1/master/cities` |

### Section 4 — Vehicle & Crew (Fleet — Preferred)

If the company has registered vehicles in Fleet, use these FK fields. They auto-populate `vehicle_info` snapshot on the backend.

| Field | Label | Type | API Source |
|---|---|---|---|
| `fleet_id` | Vehicle | Searchable dropdown | `GET /v1/fleet?status=ACTIVE` — shows `vehicle_no`, `make`, `model` |
| `driver_id` | Driver | Searchable dropdown | `GET /v1/fleet/staff?role=DRIVER` |
| `owner_id` | Owner | Searchable dropdown | `GET /v1/fleet/staff?role=OWNER` — optional |
| `conductor_id` | Conductor / Helper | Searchable dropdown | `GET /v1/fleet/staff?role=CONDUCTOR` — optional |

> When `fleet_id` is selected, auto-fill the vehicle number in the summary preview. When `driver_id` is selected, auto-fill driver name + mobile in the summary preview.

### Section 5 — Manual Vehicle Info (Fallback — when fleet not registered)

Only show this section if `fleet_id` is NOT selected. Stored in `vehicle_info` JSONB.

| Field | Label | Type |
|---|---|---|
| `vehicle_info.truck_no` | Truck / Vehicle Number | Text (e.g. `MH04AB1234`) |
| `vehicle_info.truck_type` | Truck Type | Select: `TRUCK / TRAILER / MINI_TRUCK / PICKUP / TANKER / OTHER` |
| `vehicle_info.owner_name` | Owner Name | Text |
| `vehicle_info.driver_name` | Driver Name | Text |
| `vehicle_info.driver_mobile` | Driver Mobile | Text |

### Section 6 — Remarks

| Field | Label | Type |
|---|---|---|
| `remarks` | Remarks / Notes | Textarea — optional |

---

## API Call to Create Trip Sheet

```
POST /v1/challan/trip-sheet
Authorization: Bearer <token>

Body:
{
  "trip_sheet_no":   "TS-001/25",
  "trip_date":       "2026-04-30",
  "from_city_id":    "<uuid>",
  "to_city_id":      "<uuid>",

  // Option A — fleet registered:
  "fleet_id":        "<uuid>",
  "driver_id":       "<uuid>",
  "owner_id":        "<uuid>",          // optional
  "conductor_id":    "<uuid>",          // optional

  // Option B — manual:
  "vehicle_info": {
    "truck_no":      "MH04AB1234",
    "truck_type":    "TRUCK",
    "driver_name":   "Ramesh Kumar",
    "driver_mobile": "9876543210",
    "owner_name":    "Suresh Transport"
  },


  "remarks":         "Direct trip MUM to DEL"
}
```

Response includes `trip_sheet_id` — use this for all subsequent operations.

---

## Cross-Branch Trip — How Branch B Joins Branch A's Trip

### The Concept

A trip sheet is **company-wide**. Branch A creates the truck trip (A→C). Branch B has some bilties going the same direction. Instead of sending a separate truck, Branch B loads its challan onto Branch A's truck.

```
Branch A's trip sheet (A → C)
  ├── Challan from Branch A  (3 bilties)
  └── Challan from Branch B  (1 bilty)   ← Branch B joins here
```

### Full Step-by-Step Flow

#### Step 1 — Branch A creates the trip sheet

```
POST /v1/challan/trip-sheet
Body: { "trip_sheet_no": "TS-101", "trip_date": "...", "from_city_id": ..., "to_city_id": ..., "fleet_id": ... }
```

#### Step 2 — Branch A creates its own challan and adds bilties

```
POST /v1/challan
POST /v1/challan/{challan_a_id}/add-bilty   Body: { "bilty_id": "..." }
```

#### Step 3 — Branch A attaches its challan to the trip sheet

```
POST /v1/challan/{challan_a_id}/move-to-trip-sheet   Body: { "trip_sheet_id": "..." }
```

#### Step 4 — Branch B discovers the open trip

```
GET /v1/challan/trip-sheet?trip_status=OPEN
```

Returns ALL open trip sheets across the company. Branch B sees Branch A's trip here.

#### Step 5 — Branch B creates its own challan and adds bilties

```
POST /v1/challan
POST /v1/challan/{branch_b_challan_id}/add-bilty
```

#### Step 6 — Branch B joins Branch A's trip sheet

```
POST /v1/challan/{branch_b_challan_id}/move-to-trip-sheet
Body: { "trip_sheet_id": "<branch_a_trip_sheet_id>" }
```

#### Step 7 — Branch A dispatches the trip

```
POST /v1/challan/trip-sheet/{trip_sheet_id}/dispatch
```

Dispatches all challans in the trip — including Branch B's.

#### Step 8 — Destination marks arrival

```
POST /v1/challan/trip-sheet/{trip_sheet_id}/arrive
```

---

## Other Branches — Viewing Co-Loaded Challans in a Trip

### The Problem

After Branch B joins Branch A's trip, both branches share the same truck. Each branch can only see their own challans in the normal challan list. But on the **Trip Sheet detail page**, both branches need to see everything loaded on that truck — including challans from other branches.

This is handled by a dedicated endpoint that returns **all challans on a trip**, tagged with `is_mine` so the frontend can split them into sections.

---

### API

```
GET /v1/challan/trip-sheet/{trip_sheet_id}/challans
Authorization: Bearer <token>
```

No query params needed — the backend uses the logged-in user's `branch_id` to set `is_mine` automatically.

---

### Response Shape

```json
[
  {
    "challan_id":        "aaaa-...",
    "challan_no":        "CH-A-001",
    "branch_id":         "<branch-A-uuid>",
    "status":            "DISPATCHED",
    "challan_date":      "2026-04-30",
    "from_branch_id":    "<uuid>",
    "to_branch_id":      "<uuid>",
    "total_bilty_count": 3,
    "total_freight":     4500.00,
    "total_weight":      180.0,
    "total_packages":    12,
    "is_mine":           false,
    "bilties": [
      {
        "bilty_id":        "...",
        "gr_no":           "GR-001",
        "bilty_date":      "2026-04-30",
        "consignor_name":  "ABC Traders",
        "consignee_name":  "XYZ Mart",
        "from_city_id":    "<uuid>",
        "to_city_id":      "<uuid>",
        "no_of_pkg":       4,
        "weight":          60.0,
        "total_amount":    1500.00,
        "delivery_type":   "DOOR",
        "payment_mode":    "TOPAY",
        "status":          "DISPATCHED"
      }
    ]
  },
  {
    "challan_id":        "bbbb-...",
    "challan_no":        "CH-B-001",
    "branch_id":         "<branch-B-uuid>",
    "is_mine":           true,
    "total_bilty_count": 1,
    "total_freight":     800.00,
    "bilties": [...]
  }
]
```

**`is_mine: true`** — challan belongs to the current user's branch.
**`is_mine: false`** — challan belongs to another branch sharing this truck.

---

### Frontend — Trip Sheet Detail Page Layout

Use two visual sections on the Trip Sheet detail page:

```
┌─────────────────────────────────────────────┐
│  Trip Sheet TS-101  │  MUM → DEL  │  DISPATCHED │
│  Truck: MH04AB1234  │  Driver: Ramesh Kumar      │
└─────────────────────────────────────────────┘

── MY CHALLAN ─────────────────────────────────
  CH-B-001   1 bilty   ₹800   Branch B
  [View bilties ▼]
    GR-001  ABC Traders → XYZ Mart  4 pkg  60kg  ₹800

── OTHER BRANCHES ─────────────────────────────
  CH-A-001   3 bilties   ₹4,500   Branch A
  [View bilties ▼]
    GR-010  Mehta & Co → Patel Store   ...
    GR-011  Ram Traders → Quick Mart   ...
    GR-012  Sharma Agro → City Hub     ...
```

**Rules:**
- Only show bilties for "My Challan" section by default (expanded)
- "Other Branches" section is collapsed by default — user taps to expand
- Each challan row shows: challan no, bilty count, freight total, branch name (look up from branch master), status badge
- Show a "View Bilties" expand/collapse on each challan row

---

### Frontend Implementation Steps

1. **On trip sheet detail page load**, call both in parallel:
   ```
   GET /v1/challan/trip-sheet/{trip_sheet_id}
   GET /v1/challan/trip-sheet/{trip_sheet_id}/challans
   ```

2. **Split the challans array** on `is_mine`:
   ```js
   const myChallans    = challans.filter(c => c.is_mine);
   const otherChallans = challans.filter(c => !c.is_mine);
   ```

3. **Render two sections** — "My Challan" and "Other Branches".

4. **Branch name display** — `branch_id` is a UUID. Map it to a branch name using the company's branch list (`GET /v1/onboarding/branches` or equivalent). Cache this on app load.

5. **No edit actions** on other branches' challans — read-only view only. Actions (add bilty, remove bilty, dispatch) are only shown on `is_mine === true` rows.

---

### Edge Cases

| Situation | Behaviour | Frontend Fix |
|---|---|---|
| Only one branch on the trip | `otherChallans` is empty — hide "Other Branches" section | Check `otherChallans.length === 0` before rendering the section |
| Trip has 5+ branches | All appear under "Other Branches" grouped by challan | Each challan row shows its `branch_id` mapped to name |
| User's branch has multiple challans on same trip | All show as `is_mine: true` | "My Challan" section shows multiple rows |
| Trip sheet not found | `404` response | Show "Trip not found" error page |
| Branch not joined yet (just viewing an open trip) | `otherChallans` has all challans, `myChallans` is empty | Show prompt: "Join this trip to add your challan" |

---

## API Quick Reference — Trip Sheet

| Action | Method | Endpoint |
|---|---|---|
| Create trip sheet | POST | `/v1/challan/trip-sheet` |
| List all trip sheets (company-wide) | GET | `/v1/challan/trip-sheet` |
| Get trip sheet with challans (summary) | GET | `/v1/challan/trip-sheet/{id}` |
| **Get all challans on a trip (cross-branch)** | **GET** | **`/v1/challan/trip-sheet/{id}/challans`** |
| Update trip sheet | PUT | `/v1/challan/trip-sheet/{id}` |
| Dispatch trip sheet | POST | `/v1/challan/trip-sheet/{id}/dispatch` |
| Mark trip as arrived | POST | `/v1/challan/trip-sheet/{id}/arrive` |
| Add challan to trip | POST | `/v1/challan/{challan_id}/move-to-trip-sheet` |
| Remove challan from trip | POST | `/v1/challan/{challan_id}/remove-from-trip-sheet` |
| List available vehicles | GET | `/v1/fleet?status=ACTIVE` |
| List drivers | GET | `/v1/fleet/staff?role=DRIVER` |
| List cities | GET | `/v1/master/cities` |
| List transporters | GET | `/v1/master/transports` |
