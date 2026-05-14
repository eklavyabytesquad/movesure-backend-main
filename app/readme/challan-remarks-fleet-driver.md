# Challan — Remarks, Fleet & Driver Details

## 1. Adding a Remark at Challan Creation

`remarks` is a plain `TEXT` field on the `challan` table.  
Pass it directly in the **POST /challan** request body.

### Request — `POST /api/v1/challan`

```json
{
  "challan_no": "CH/0012",
  "challan_date": "2026-05-05",
  "from_branch_id": "<uuid>",
  "to_branch_id": "<uuid>",
  "remarks": "Fragile goods — handle with care",
  "fleet_id": "<fleet-uuid>",
  "driver_id": "<fleet-staff-uuid>"
}
```

- `remarks` is **optional** — omit if not needed.
- It can be updated later via `PATCH /api/v1/challan/{challan_id}` with `{ "remarks": "updated note" }`.
- `remarks` also exists on `challan_trip_sheet` — use the same pattern there.

---

## 2. Linking Fleet & Driver to a Challan

All four FK fields are optional. Prefer these over the legacy `vehicle_info` JSONB snapshot.

| Field | Table | Role |
|---|---|---|
| `fleet_id` | `fleet` | The registered vehicle (truck) |
| `driver_id` | `fleet_staff` | Staff with `role = DRIVER` |
| `owner_id` | `fleet_staff` | Staff with `role = OWNER` |
| `conductor_id` | `fleet_staff` | Staff with `role = CONDUCTOR` |

### How to get valid IDs before creating the challan

```
GET /api/v1/fleet                          → lists all vehicles → pick fleet_id
GET /api/v1/fleet/staff?role=DRIVER        → lists drivers     → pick driver_id
GET /api/v1/fleet/staff?role=OWNER         → lists owners      → pick owner_id
GET /api/v1/fleet/staff?role=CONDUCTOR     → lists conductors  → pick conductor_id
```

### Challan creation with fleet + driver

```json
{
  "fleet_id":    "f1a2b3c4-...",
  "driver_id":   "d9e8f7a6-...",
  "owner_id":    "a1b2c3d4-...",
  "conductor_id": null,
  "remarks": "Night trip — confirm arrival by 6 AM"
}
```

---

## 3. Fetching Fleet & Driver Details of a Challan

`GET /api/v1/challan/{challan_id}` returns the full challan row.  
The response includes the raw FK columns:

```json
{
  "challan_id": "...",
  "challan_no": "CH/0012",
  "remarks": "Night trip — confirm arrival by 6 AM",
  "fleet_id": "f1a2b3c4-...",
  "driver_id": "d9e8f7a6-...",
  "owner_id": "a1b2c3d4-...",
  "conductor_id": null,
  "vehicle_info": {},
  ...
}
```

To get the **full fleet/driver detail objects**, make separate calls:

```
GET /api/v1/fleet/{fleet_id}              → vehicle details (vehicle_no, truck_type, etc.)
GET /api/v1/fleet/staff/{driver_id}       → driver details  (name, mobile, license_no, etc.)
GET /api/v1/fleet/staff/{owner_id}        → owner details
```

> **Note:** The `vehicle_info` JSONB field is a legacy snapshot (truck_no, driver_name, etc.).  
> It is **not** kept in sync automatically. Always use `fleet_id` / `driver_id` FKs as the source of truth.

---

## 4. Updating Remarks / Fleet After Creation

```
PATCH /api/v1/challan/{challan_id}

{
  "remarks": "Revised note",
  "driver_id": "<new-driver-uuid>"
}
```

Only dispatched challans (`status = DISPATCHED / ARRIVED_HUB / CLOSED`) should not have their fleet fields changed without care.
