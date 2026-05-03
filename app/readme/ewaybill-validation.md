# E-Way Bill Validation — Integration Guide

Covers two APIs:
1. **`GET /v1/ewaybill/validate`** — fetch EWB from NIC + save to DB + return validation summary
2. **`GET /v1/ewaybill/validation-history`** — return full versioned history for any saved EWB

Use these together to show **"Already Validated"** badges, validation counts, and status timelines on the frontend.

---

## 1. Validate (Fetch from NIC)

```
GET /v1/ewaybill/validate?eway_bill_number={12-digit}&bilty_id={uuid}
Authorization: Bearer <jwt>
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `eway_bill_number` | string | ✅ | 12-digit E-Way Bill number |
| `bilty_id` | UUID string | ❌ | Link this EWB to a bilty |

**What it does:**
- Calls NIC (Masters India) to get live EWB details
- Upserts `ewb_records` with the latest NIC state
- **Inserts a new row in `ewb_validation_log` with the next `version_no`** ← was broken, now fixed
- Inserts an event row in `ewb_events`

**Response:**
```json
{
  "status": "success",
  "message": "E-Way Bill details retrieved successfully",
  "data": { ...full NIC response... },

  "is_previously_validated": true,
  "total_validations": 3,
  "latest_version_no": 3,
  "latest_nic_status": "ACTIVE",
  "latest_validated_at": "2026-05-03T10:22:00Z",

  "ewb_record_id": "uuid-of-the-ewb_records-row"
}
```

`is_previously_validated` is `true` from the **second** call onwards (i.e., if the same EWB was fetched before). Use this to show the badge.

---

## 2. Validation History

```
GET /v1/ewaybill/validation-history?eway_bill_number={12-digit}
Authorization: Bearer <jwt>
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `eway_bill_number` | string | ✅ | 12-digit E-Way Bill number |

**Returns the full versioned log of every NIC check.** The EWB must have been fetched at least once first (via `/validate`). If not, returns 404 with a helpful hint.

**Response:**
```json
{
  "status": "success",
  "eway_bill_number": "382241586928",
  "is_previously_validated": true,
  "total_validations": 3,
  "latest_version_no": 3,
  "latest_nic_status": "ACTIVE",
  "latest_validated_at": "2026-05-03T10:22:00Z",
  "current_ewb_status": "ACTIVE",
  "current_valid_upto": "2026-05-06T23:59:00Z",
  "ewb_id": "uuid-of-ewb_records-row",
  "history": [
    {
      "log_id": "uuid",
      "ewb_id": "uuid",
      "eway_bill_number": "382241586928",
      "version_no": 3,
      "nic_status": "ACTIVE",
      "valid_upto": "2026-05-06T23:59:00Z",
      "generated_by_gstin": "07ABCPC0876F1Z1",
      "vehicle_number": "HR58C8435",
      "transporter_id": "07ABCPC0876F1Z1",
      "error_code": null,
      "error_description": null,
      "triggered_by": "manual",
      "validated_at": "2026-05-03T10:22:00Z",
      "created_by": "user-uuid"
    },
    {
      "version_no": 2,
      "nic_status": "ACTIVE",
      "valid_upto": "2026-05-04T23:59:00Z",
      "validated_at": "2026-05-02T09:10:00Z",
      ...
    },
    {
      "version_no": 1,
      "nic_status": "ACTIVE",
      "validated_at": "2026-05-01T14:05:00Z",
      ...
    }
  ]
}
```

History is returned **newest first** (highest `version_no` first).

---

## `triggered_by` values

| Value | When |
|---|---|
| `manual` | User clicked "Validate" on the UI — or called `/validate` API directly |
| `auto` | Background cron / scheduled check |
| `on_generate` | Auto-check immediately after generating a new EWB |
| `on_bilty_save` | Auto-check when a bilty is saved |

---

## Frontend Integration

### "Already Validated" Badge

Call `/validation-history` when loading the EWB detail page:

```jsx
const [validationInfo, setValidationInfo] = useState(null);

useEffect(() => {
  fetch(`/v1/ewaybill/validation-history?eway_bill_number=${ewbNumber}`, {
    headers: { Authorization: `Bearer ${authToken}` },
  })
    .then(r => r.json())
    .then(data => {
      if (data.status === "success") setValidationInfo(data);
    })
    .catch(() => {}); // EWB not yet fetched — badge just won't show
}, [ewbNumber]);

// Badge component
{validationInfo?.is_previously_validated && (
  <span className="badge badge-success">
    ✅ Validated {validationInfo.total_validations}x — last {timeAgo(validationInfo.latest_validated_at)}
  </span>
)}
```

### Validation History Timeline

```jsx
export function ValidationHistory({ ewbNumber, authToken }) {
  const [data, setData] = useState(null);

  const load = () =>
    fetch(`/v1/ewaybill/validation-history?eway_bill_number=${ewbNumber}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    })
      .then(r => r.json())
      .then(setData);

  useEffect(() => { load(); }, [ewbNumber]);

  if (!data) return <p>Loading...</p>;
  if (!data.is_previously_validated) return <p>Not yet validated.</p>;

  return (
    <div>
      <h3>Validation History ({data.total_validations} checks)</h3>
      <table>
        <thead>
          <tr>
            <th>#</th><th>Status</th><th>Valid Until</th>
            <th>Vehicle</th><th>Error</th><th>Checked At</th>
          </tr>
        </thead>
        <tbody>
          {data.history.map(row => (
            <tr key={row.log_id}>
              <td>v{row.version_no}</td>
              <td>{row.nic_status ?? (row.error_code ? "ERROR" : "—")}</td>
              <td>{row.valid_upto ? new Date(row.valid_upto).toLocaleString() : "—"}</td>
              <td>{row.vehicle_number ?? "—"}</td>
              <td>{row.error_code ? `${row.error_code}: ${row.error_description}` : "—"}</td>
              <td>{new Date(row.validated_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

### Re-validate Button (force a fresh NIC check)

```jsx
const revalidate = async () => {
  const res = await fetch(
    `/v1/ewaybill/validate?eway_bill_number=${ewbNumber}`,
    { headers: { Authorization: `Bearer ${authToken}` } }
  );
  const data = await res.json();
  // data.total_validations is now incremented by 1
  // data.is_previously_validated is true
  setValidationInfo(data);
};

<button onClick={revalidate}>🔄 Re-validate from NIC</button>
```

---

## What was broken and what was fixed

| Bug | Root cause | Fix |
|---|---|---|
| Validation log rows never inserted | `ewb_record.get("id")` — wrong key; Supabase returns PK as `ewb_id` | Changed to `ewb_record.get("ewb_id")` |
| DB insert fails with column error | Code wrote to `ewb_status`, `nic_snapshot`, `transporter_name` — none of these columns exist in `ewb_validation_log` | Corrected to `nic_status`; removed non-existent columns |
| CHECK constraint violation on insert | `triggered_by="FETCH"` is not a valid DB enum value | Changed to `"manual"`; all callers validated against allowed set |
| `/validate` response had no history info | No validation count was returned | Response now includes `is_previously_validated`, `total_validations`, `latest_nic_status`, `latest_validated_at` |
