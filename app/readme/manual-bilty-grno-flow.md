# Manual Bilty — GR Number Auto-fill Flow

## Overview

For MANUAL bilties the GR number is entered by the user (not auto-incremented by
the DB sequence). However, if the selected book has a series defined, the backend
can **preview** the next available number so the form auto-fills it.

**Key rule:** `GET /v1/bilty/peek-gr/{book_id}` is **read-only** — it never
consumes the number. The counter only advances when `POST /v1/bilty` is called.

---

## Step-by-step Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Page load — populate the "Book" dropdown                     │
│    GET /v1/bilty-setting/books?bilty_type=MANUAL                │
│    (or /v1/bilty-setting/books/all to include all branches)     │
└──────────────────────────┬──────────────────────────────────────┘
                           ↓ user selects a book
┌─────────────────────────────────────────────────────────────────┐
│ 2. Auto-fill GR No field                                        │
│    GET /v1/bilty/peek-gr/{book_id}                              │
└──────────────────────────┬──────────────────────────────────────┘
                           ↓ prefill input; user may override
┌─────────────────────────────────────────────────────────────────┐
│ 3. User fills form and clicks Save                              │
│    POST /v1/bilty                                               │
│    { bilty_type: "MANUAL", book_id: "...", gr_no: "...", ... }  │
└─────────────────────────────────────────────────────────────────┘
```

---

## API Reference

### Step 1 — List MANUAL books for the dropdown

```
GET /v1/bilty-setting/books?bilty_type=MANUAL&is_active=true
```

**Response:**
```json
{
  "count": 2,
  "books": [
    {
      "book_id":       "cc656f8f-bbd3-4756-8115-488b4242e560",
      "book_name":     "MANUAL-MGL",
      "bilty_type":    "MANUAL",
      "branch_id":     "0c15b4c4-3d14-4c68-af43-c8ce7e738fd7",
      "prefix":        "MUM/",
      "from_number":   1,
      "to_number":     500,
      "current_number": 41,
      "digits":        4,
      "postfix":       "/26",
      "is_active":     true,
      "is_completed":  false,
      "book_defaults": {
        "delivery_type": "GODOWN",
        "payment_mode":  "TO-PAY",
        "from_city_id":  "f416e290-b5c1-47d3-a4e3-fe174a99540f"
      }
    }
  ]
}
```

> Use `book_name` as the dropdown label.
> Optionally show `prefix` + series range in the label: **"MANUAL-MGL (MUM/0001–0500)"**.

---

### Step 2 — Peek next GR number (on book selection)

```
GET /v1/bilty/peek-gr/{book_id}
```

**Response — book has a series:**
```json
{
  "gr_no":        "MUM/0042/26",
  "gr_number":    42,
  "book_id":      "cc656f8f-bbd3-4756-8115-488b4242e560",
  "book_name":    "MANUAL-MGL",
  "bilty_type":   "MANUAL",
  "is_exhausted": false,
  "has_series":   true
}
```

**Response — MANUAL book with no series (free-entry):**
```json
{
  "gr_no":        null,
  "gr_number":    null,
  "book_id":      "...",
  "book_name":    "MANUAL-FREE",
  "bilty_type":   "MANUAL",
  "is_exhausted": false,
  "has_series":   false
}
```

**Frontend handling:**

```js
async function onBookSelected(bookId) {
  const res = await api.get(`/v1/bilty/peek-gr/${bookId}`);

  if (res.is_exhausted) {
    showWarning("This book is exhausted. Please select another book.");
    setGrNoField("");
    return;
  }

  if (res.has_series && res.gr_no) {
    setGrNoField(res.gr_no);   // auto-fill; user can still edit
  } else {
    setGrNoField("");           // no series — user types GR freely
  }
}
```

---

### Step 3 — Create the bilty

```
POST /v1/bilty
Content-Type: application/json
```

**Minimum payload (MANUAL):**
```json
{
  "bilty_type": "MANUAL",
  "book_id":    "cc656f8f-bbd3-4756-8115-488b4242e560",
  "gr_no":      "MUM/0042/26"
}
```

**Full payload:**
```json
{
  "bilty_type":     "MANUAL",
  "book_id":        "cc656f8f-bbd3-4756-8115-488b4242e560",
  "gr_no":          "MUM/0042/26",
  "bilty_date":     "2026-05-04",

  "consignor_id":   "uuid-or-null",
  "consignee_id":   "uuid-or-null",
  "from_city_id":   "f416e290-b5c1-47d3-a4e3-fe174a99540f",
  "to_city_id":     "uuid-or-null",

  "delivery_type":  "GODOWN",
  "payment_mode":   "TO-PAY",

  "transport_id":   null,
  "transport_name": "RGT LOGISTICS",
  "vehicle_no":     "MH04AB1234",

  "packages":       1,
  "weight_kg":      100.0,
  "charged_weight": 100.0,
  "freight":        500.0,

  "remarks":        null,
  "metadata":       {}
}
```

**Success response (201):**
```json
{
  "bilty_id": "new-uuid",
  "gr_no":    "MUM/0042/26",
  "bilty_type": "MANUAL",
  ...
}
```

**Error — gr_no missing:**
```json
{ "detail": "gr_no is required for MANUAL bilties." }
```

---

## Important Notes

| Point | Detail |
|-------|--------|
| `peek-gr` is non-destructive | Safe to call every time the user changes the book selection |
| `gr_no` is editable | User can always type a different number — backend saves whatever is sent |
| Counter advances on `POST /v1/bilty` | The DB function `fn_next_gr_no` is called inside the create flow only for REGULAR books; for MANUAL the counter is NOT auto-advanced — you must manage it or it stays as-is |
| Duplicate GR guard | There is no uniqueness constraint on `gr_no` per-book — prevent duplicates on the frontend by always using the peek value as the default |
| Book defaults auto-applied | If the selected MANUAL book has `book_defaults`, the backend fills `delivery_type`, `payment_mode`, `from_city_id`, `to_city_id`, `transport_id` automatically when those fields are omitted from the POST body |

---

## Endpoint Summary

| Method | URL | Purpose |
|--------|-----|---------|
| `GET` | `/v1/bilty-setting/books?bilty_type=MANUAL` | List MANUAL books for dropdown |
| `GET` | `/v1/bilty-setting/books/all?bilty_type=MANUAL` | Same, all branches |
| `GET` | `/v1/bilty/peek-gr/{book_id}` | Preview next GR (non-destructive) |
| `POST` | `/v1/bilty` | Create bilty (saves GR, advances counter for REGULAR only) |
