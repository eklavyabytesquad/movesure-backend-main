# Manual Bilty — Guide

## What is a Manual Bilty?

A **Manual Bilty** (also called a Station Bilty or Hand Bilty) is a bilty where the GR number is written by hand on a physical paper — not generated from a book series.

- The staff member physically writes any number on the paper
- That exact number is typed into the system
- There is no prefix, no series, no auto-increment
- `bilty_type = "MANUAL"`, `book_id` is `null` unless a MANUAL book is linked (see below)

---

## How it Differs from a Regular Bilty

| | REGULAR | MANUAL |
|---|---|---|
| GR number source | Auto-generated from book (`fn_next_gr_no`) | Typed freely by staff |
| Book required | Yes — primary REGULAR book must exist | Optional — a MANUAL book can exist for defaults only |
| Prefix / series | Yes — as configured in the book | None — raw number entered on the physical paper |
| Auto-continue | Supported via book settings | Not applicable |
| `book_id` in DB | Set to the book UUID | Set to the MANUAL book UUID (if one exists), else `null` |
| `bilty_type` | `REGULAR` | `MANUAL` |

---

## MANUAL Bilty Book — What is it?

A **MANUAL bilty book** is not a number series. It has **no `from_number` / `to_number`** — those fields are left empty.

Its only purpose is to store **`book_defaults`**: pre-fill values that the frontend should auto-load when the staff opens the manual bilty form. This saves time — staff don't have to fill in the same city or payment mode every time.

### What can be stored in book_defaults?

| Key | Description | Example |
|---|---|---|
| `from_city_id` | Default origin city UUID | `"uuid-of-mumbai"` |
| `to_city_id` | Default destination city UUID | `"uuid-of-delhi"` |
| `delivery_type` | Default delivery type | `"DOOR"` or `"GODOWN"` |
| `payment_mode` | Default payment mode | `"TO-PAY"` or `"PAID"` or `"FOC"` |
| `transport_id` | Default transporter UUID | `"uuid-of-transport"` |

---

## Step 1 — Create a MANUAL Bilty Book

```
POST /v1/bilty-setting/books
Authorization: Bearer <token>

{
  "book_name":   "Station Bilty Book",
  "bilty_type":  "MANUAL",

  "book_defaults": {
    "from_city_id":   "<uuid-of-your-city>",
    "delivery_type":  "DOOR",
    "payment_mode":   "TO-PAY"
  }
}
```

**Do NOT send `from_number`, `to_number`, `prefix`, `postfix`, `digits`** — the backend will reject with `422` if you include them for a MANUAL book.

Response includes `book_id` — use this in Step 2.

---

## Step 2 — Mark it as the Primary MANUAL Book

```
POST /v1/bilty-setting/books/{book_id}/set-primary
Authorization: Bearer <token>
```

Only one MANUAL book can be primary per branch at a time. Once set as primary, every manual bilty created will automatically pick up this book's `book_defaults`.

---

## Step 3 — Create a Manual Bilty

```
POST /v1/bilty
Authorization: Bearer <token>

{
  "bilty_type":     "MANUAL",
  "gr_no":          "1234",

  "consignor_name": "Mehta Traders",
  "consignee_name": "Patel Mart",

  "no_of_pkg":      3,
  "weight":         45.0,
  "total_amount":   1200.0,

  "status": "SAVED"
}
```

The backend will:
1. Validate that `gr_no` is provided
2. Look up the primary MANUAL book for this branch
3. Apply any `book_defaults` that were NOT provided in the request body (e.g. `from_city_id`, `payment_mode`)
4. Store `book_id` on the bilty pointing to the MANUAL book
5. Proceed with creation and auto-assign to the primary challan (if status = SAVED)

**Fields provided in the request always override book defaults.** Defaults only fill in fields that were omitted.

---

## GR Number Rules for Manual Bilties

- **No series, no format enforced** — `gr_no` is whatever is written on the physical paper
- **No duplicate check** — two staff members can type the same GR number; the physical paper is the source of truth
- **Any format accepted** — `"1234"`, `"SB/25/001"`, `"HAND-01"` — all valid up to 50 characters

---

## Frontend — Create Manual Bilty Form

### Toggle on the Bilty Creation Screen

```
[ Regular Bilty ]   [ Manual / Station Bilty ]
```

When **Manual Bilty** is selected:
1. **Hide** the book selector and "Auto-generate GR" button
2. **Show** a plain text input: **"GR Number / Bilty No."** (required)
3. **Auto-fill** `from_city_id`, `payment_mode`, `delivery_type` etc. from the primary MANUAL book's defaults — but allow staff to override

### How to load book defaults on the frontend

```
GET /v1/bilty-setting/books/primary?bilty_type=MANUAL
Authorization: Bearer <token>
```

Returns the primary MANUAL book. Read `book.book_defaults` and pre-fill the form. If no primary MANUAL book exists (returns 404), show the form blank.

---

## Listing Manual Bilties

```
GET /v1/bilty?bilty_type=MANUAL
Authorization: Bearer <token>
```

To list only REGULAR bilties:
```
GET /v1/bilty?bilty_type=REGULAR
```

---

## Common Mistakes

| Mistake | Error | Fix |
|---|---|---|
| Sending `bilty_type: "MANUAL"` but no `gr_no` | `422 — gr_no is required for MANUAL bilties` | Always include `gr_no` |
| Sending `from_number` or `to_number` in `POST /v1/bilty-setting/books` for a MANUAL book | `422 — from_number and to_number must not be set for MANUAL books` | Leave both out for MANUAL books |
| Expecting auto-generated GR on a MANUAL bilty | No GR is generated | Must provide `gr_no` manually |
| Not marking the MANUAL book as primary | `book_defaults` are never applied | Call `POST /books/{id}/set-primary` after creation |
| Calling `GET /v1/bilty/next-gr` before creating a MANUAL bilty | That endpoint is only for REGULAR books | Skip it entirely for manual bilties |


## What is a Manual Bilty?

A **Manual Bilty** (also called a Station Bilty or Hand Bilty) is a bilty where the GR number is written by hand on a physical paper — not generated from a book series.

- The staff member physically writes any number on the paper
- That exact number is typed into the system
- There is no prefix, no series, no auto-increment, no book involved
- `bilty_type = "MANUAL"`, `book_id` is always `null`

---

## How it Differs from a Regular Bilty

| | REGULAR | MANUAL |
|---|---|---|
| GR number source | Auto-generated from book (fn_next_gr_no) | Typed freely by staff |
| Book required | Yes — primary REGULAR book must exist | No book needed at all |
| Prefix / series | Yes — as configured in the book | None — raw number |
| Auto-continue | Supported via book settings | Not applicable |
| `book_id` in DB | Set to the book UUID | Always `null` |
| `bilty_type` | `REGULAR` | `MANUAL` |

---

## API — Creating a Manual Bilty

```
POST /v1/bilty
Authorization: Bearer <token>

{
  "bilty_type":      "MANUAL",
  "gr_no":           "1234",

  "consignor_name":  "Mehta Traders",
  "consignor_mobile": "9876543210",

  "consignee_name":  "Patel Mart",
  "from_city_id":    "<uuid>",
  "to_city_id":      "<uuid>",

  "payment_mode":    "TO-PAY",
  "delivery_type":   "DOOR",

  "no_of_pkg":       3,
  "weight":          45.0,
  "total_amount":    1200.0,

  "status":          "SAVED"
}
```

**Key rules:**
- `bilty_type` must be `"MANUAL"`
- `gr_no` is **required** — the backend will reject the request with `422` if it is missing
- Do NOT send `book_id` — leave it out entirely (it will be stored as `null`)
- The GR number can be any string: `"1234"`, `"STN/99"`, `"HAND-01"` — whatever is written on the paper
- All other fields (charges, consignor, consignee, route) work exactly the same as a REGULAR bilty

---

## GR Number Rules for Manual Bilties

Since there is no book enforcing uniqueness on MANUAL bilties, consider these points:

- **No duplicate check on the backend** — if two staff members type the same GR number for two different MANUAL bilties, both will be saved. The physical paper is the source of truth.
- **Any format is accepted** — numbers only (`"1234"`), alphanumeric (`"SB/25/001"`), or free text are all valid since `gr_no` is a `VARCHAR(50)`.
- **The GR number is exactly what is printed on the physical bilty** — staff should copy it exactly, including any prefix written by hand.

---

## Frontend — Create Manual Bilty Form

### Toggle on the Bilty Creation Screen

Add a toggle or tab at the top of the create-bilty screen:

```
[ Regular Bilty ]   [ Manual / Station Bilty ]
```

When **Manual Bilty** is selected:

1. **Hide** the book selector and "Auto-generate GR" button entirely
2. **Show** a plain text input labeled **"GR Number / Bilty No."** — required field
3. All other form sections (consignor, consignee, route, charges) remain unchanged

### Form Fields Unique to Manual Bilty

| Field | Label | Type | Notes |
|---|---|---|---|
| `gr_no` | GR Number / Bilty No. | Text (required) | Whatever is written on the physical paper — no validation on format |
| `bilty_type` | (hidden) | hardcoded `"MANUAL"` | Never shown to user — set automatically |

Everything else (consignor, consignee, route, charges, payment mode, delivery type) is identical to the regular bilty form.

### Validation on the Frontend

- `gr_no` must not be empty — show inline error: `"GR number is required for manual bilties"`
- Max 50 characters (matches DB column)
- No format validation — accept whatever the staff types

---

## What Happens After Creation

Manual bilties behave identically to REGULAR bilties after creation:

- If `status = "SAVED"` → auto-assigned to the branch's primary challan (same as REGULAR)
- If `status = "DRAFT"` → saved as draft, not assigned to any challan
- Can be added to challans, dispatched, tracked through the full lifecycle
- Appear in `GET /v1/bilty` list — filter by `bilty_type=MANUAL` to see only manual bilties
- Can be printed using the branch's primary template

---

## Listing Manual Bilties Only

```
GET /v1/bilty?bilty_type=MANUAL
Authorization: Bearer <token>
```

To list only REGULAR bilties:
```
GET /v1/bilty?bilty_type=REGULAR
```

---

## Common Mistakes

| Mistake | Error | Fix |
|---|---|---|
| Sending `bilty_type: "MANUAL"` but no `gr_no` | `422 — gr_no is required for MANUAL bilties` | Always include `gr_no` for manual bilties |
| Sending `book_id` with a MANUAL bilty | Book lookup is ignored — `book_id` is stored as null | Do not send `book_id` for manual bilties |
| Expecting auto-generated GR on a MANUAL bilty | No GR is generated — field stays blank | Must provide `gr_no` manually |
| Trying to call `GET /v1/bilty/next-gr` before creating a MANUAL bilty | That endpoint is only for REGULAR books | Skip it entirely for manual bilties |
