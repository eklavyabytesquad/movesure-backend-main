# Cross-Branch Challan & Bilty Transfer Guide

## Understanding the Root Problem

### Why Branch A sees Branch B's challans

Every `challan` row has **three** branch-related columns:

| Column | Meaning |
|---|---|
| `branch_id` | The branch that **created** the challan (owner) |
| `from_branch_id` | The dispatch origin branch |
| `to_branch_id` | The destination / receiving branch |

The backend list endpoint `GET /v1/challan` filters by `branch_id` (the owner). If the frontend is calling this endpoint **without** passing the user's branch context, or if it is also querying by `to_branch_id`, it will mix both Branch B's own challans and challans addressed to Branch A into the same list. That is the root cause of the unwanted cross-branch visibility.

---

## Part 1 — Frontend Fix: Correct Challan Visibility

### Rule

> A branch should **only see challans it owns** on the main Challan page.  
> Challans from other branches that are **inbound** (headed toward this branch) are shown on a **separate "Incoming" tab**.

### Implementation

**Tab 1 — My Challans (default tab)**

Call:
```
GET /v1/challan?is_active=true
```
The backend automatically scopes this to `branch_id = current_user.branch_id`. No extra filter needed. This shows only challans that this branch created.

**Tab 2 — Incoming Challans**

The backend does NOT have a dedicated "incoming" endpoint yet (see Part 3 below for the backend addition needed). Until then, the frontend can approximate by calling:
```
GET /v1/challan?is_active=true
```
...with an additional client-side filter after the response:
```ts
const incoming = allChallans.filter(
  c => c.to_branch_id === currentUser.branch_id && c.branch_id !== currentUser.branch_id
);
```

But the correct long-term solution is to add the backend endpoint described in Part 3.

### What NOT to do in the frontend

- Do **not** call `GET /v1/challan` without branch scoping and then display every result
- Do **not** mix `to_branch_id`-based results with `branch_id`-based results in the same list
- Do **not** show a Branch B challan in Branch A's main "My Challans" list even if it is addressed to Branch A

---

## Part 1 — If Branch B Wants Branch A to See Their Challan

Branch B can legitimately share/expose a challan to Branch A through the normal **dispatch workflow**. Once a challan is **DISPATCHED**, Branch A should see it as an incoming shipment.

### Step-by-step flow for Branch B

1. **Create a challan** with the destination set to Branch A:

   ```
   POST /v1/challan
   Body:
   {
     "from_branch_id": "<branch_b_id>",
     "to_branch_id":   "<branch_a_id>",
     "remarks":        "Dispatch to Branch A"
   }
   ```
   The backend auto-claims a challan number from Branch B's primary book.

2. **Add bilties** to the challan (bilties that need to go to Branch A):

   ```
   POST /v1/challan/{challan_id}/add-bilty
   Body: { "bilty_id": "<bilty_id>" }
   ```
   Repeat for each bilty.

3. **Mark the challan as primary** (optional — makes it the default for new bilty auto-assignment):

   ```
   POST /v1/challan/{challan_id}/set-primary
   ```

4. **Dispatch the challan** (this is when Branch A becomes aware of it):

   ```
   POST /v1/challan/{challan_id}/dispatch
   ```
   - Challan status → `DISPATCHED`
   - `is_primary` flag cleared automatically (dispatched challan can no longer receive new bilties)
   - All bilties on the challan: status → `DISPATCHED`, `is_dispatched = true`, `dispatched_at` filled

5. **Branch A receives it** — when the vehicle arrives, Branch A's staff clicks "Arrived":

   ```
   POST /v1/challan/{challan_id}/arrive-hub
   ```
   - Challan status → `ARRIVED_HUB`
   - All bilties: status → `REACHED_HUB`, `is_reached_hub = true`

### What Branch A sees in the Incoming tab

After dispatch, Branch A queries:
```
GET /v1/challan?is_active=true
```
Then filters on the frontend for:
- `to_branch_id === branch_a_id`
- `status IN ["DISPATCHED", "ARRIVED_HUB"]`

Or once the dedicated incoming endpoint is added (Part 3):
```
GET /v1/challan/incoming
```

### Challan Settings option for Branch B

In the **Challan Settings** page for Branch B, you need a field when creating or editing a challan book:

- **Route Scope** → choose `FIXED_ROUTE`
- **From Branch** → Branch B (auto-filled from current branch)
- **To Branch** → pick from dropdown of all branches in the company

This creates a dedicated challan book for the B→A route. Every time a challan is created from this book, `from_branch_id` and `to_branch_id` are automatically set. Staff at Branch B don't need to fill them manually.

API to create such a book:
```
POST /v1/challan/book
Body:
{
  "book_name":      "B to A Route Book FY25-26",
  "route_scope":    "FIXED_ROUTE",
  "from_branch_id": "<branch_b_id>",
  "to_branch_id":   "<branch_a_id>",
  "prefix":         "B-A/",
  "from_number":    1,
  "to_number":      500,
  "digits":         4,
  "is_primary":     true
}
```

---

## Part 3 — Backend: Add Incoming Challans Endpoint

Add this to `app/services/challan/service.py`:

```python
def list_incoming_challans(
    company_id: str,
    to_branch_id: str,
    challan_status: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    is_active: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> list:
    """
    Challans dispatched FROM another branch TO this branch.
    Excludes challans owned by this branch itself.
    """
    db = get_client()
    q = (
        db.table("challan")
        .select("*")
        .eq("company_id", company_id)
        .eq("to_branch_id", to_branch_id)
        .neq("branch_id", to_branch_id)          # not owned by this branch
        .eq("is_active", is_active)
        .in_("status", ["DISPATCHED", "ARRIVED_HUB", "CLOSED"])
        .order("challan_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .offset(offset)
    )
    if challan_status:
        q = q.eq("status", challan_status)
    if from_date:
        q = q.gte("challan_date", from_date)
    if to_date:
        q = q.lte("challan_date", to_date)
    return q.execute().data or []
```

Add to `app/v1/challan.py` (before the `/{challan_id}` route):

```python
@router.get("/incoming", summary="List challans dispatched to this branch from other branches")
def api_incoming_challans(
    challan_status: str | None = Query(None, pattern="^(DISPATCHED|ARRIVED_HUB|CLOSED)$"),
    from_date:      str | None = Query(None),
    to_date:        str | None = Query(None),
    is_active:      bool       = Query(True),
    limit:          int        = Query(50, ge=1, le=200),
    offset:         int        = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    return list_incoming_challans(
        current_user["company_id"], current_user["branch_id"],
        challan_status, from_date, to_date, is_active, limit, offset,
    )
```

---

## Part 4 — Transferring a Single Bilty from Branch A to Branch B

This is the most common day-to-day operation. Here is the complete flow.

### Scenario

A bilty was created at Branch A (consignor is in City X, consignee is in City Y which is Branch B's territory). Branch A needs to transfer this single bilty to Branch B.

### Step-by-step

#### Step 1 — Create or reuse a dispatch challan at Branch A

If Branch A already has an open `FIXED_ROUTE` challan for the A→B leg, use it:
```
GET /v1/challan/primary       → check if primary challan exists and its to_branch_id = B
```
Or find the specific route challan:
```
GET /v1/challan/book/by-route?from_branch_id=<A>&to_branch_id=<B>
```
Then create a challan from that book:
```
POST /v1/challan
Body:
{
  "from_branch_id": "<branch_a_id>",
  "to_branch_id":   "<branch_b_id>"
}
```

#### Step 2 — Add the specific bilty to the challan

```
POST /v1/challan/{challan_id}/add-bilty
Body: { "bilty_id": "<the_bilty_id>" }
```

**Edge cases here:**
- If the bilty is already on another challan → backend returns `409 Conflict: "Bilty is already assigned to a challan — remove it first"`
  - Fix: call `POST /v1/challan/{old_challan_id}/remove-bilty/{bilty_id}` first
- If the bilty's status is `DISPATCHED` or later → it cannot be re-added to a new challan. The bilty has already left.
- If the bilty is a `DRAFT` → it will not appear in `available-bilties`. Confirm (save) it first via `PUT /v1/bilty/{bilty_id}` with `{ "status": "SAVED" }`.

#### Step 3 — Dispatch the challan from Branch A

```
POST /v1/challan/{challan_id}/dispatch
```

This:
- Sets challan `status = DISPATCHED`
- Sets the bilty's `status = DISPATCHED`, `is_dispatched = true`, `dispatched_challan_no = challan_no`
- Clears `is_primary` on the challan so no new bilties auto-attach

#### Step 4 — Branch B receives the challan

Branch B sees the challan in their **Incoming** tab (`GET /v1/challan/incoming`).

Branch B staff clicks "Arrive" to confirm receipt:
```
POST /v1/challan/{challan_id}/arrive-hub
```

This sets bilty `status = REACHED_HUB`, `is_reached_hub = true`.

#### Step 5 — Branch B works on the bilty from here

The bilty `branch_id` still belongs to Branch A (it was created there). Branch B can:
- View the bilty via `GET /v1/challan/{challan_id}/bilties`
- Update delivery status via `PUT /v1/bilty/{bilty_id}` (mark OUT_FOR_DELIVERY, DELIVERED, etc.)

---

## Edge Cases Summary

| Situation | What happens | Fix |
|---|---|---|
| Bilty is a DRAFT | Not shown in `available-bilties`; cannot be added to challan | Save the bilty first: `PUT /v1/bilty/{id}` `{ "status": "SAVED" }` |
| Bilty already on a challan | `409` — "Bilty is already assigned" | Remove from old challan first: `POST /v1/challan/{old_id}/remove-bilty/{bilty_id}` |
| Challan already DISPATCHED | `409` — "Cannot add bilty to a DISPATCHED challan" | Create a new challan for the transfer |
| No primary challan for branch | Auto-assign to primary challan skipped silently on bilty creation | Create a challan and set it as primary; or manually add bilty to a challan |
| Bilty already DISPATCHED/REACHED_HUB | Cannot be moved; it is already in transit | N/A — it is already with Branch B |
| Branch B tries to edit Branch A's bilty | `branch_id` mismatch; the bilty's `branch_id` is still Branch A | Allowed via `PUT /v1/bilty/{id}` since the filter is on `company_id` not `branch_id`. Guard this in the frontend by checking `bilty.branch_id !== current_user.branch_id` and showing a warning. |
| Multiple bilties to transfer | Add them all to the same challan in Step 2 (one call per bilty). Better than creating separate challans. | — |
| Branch B wants to return a bilty to Branch A | Create a new challan at Branch B with `to_branch_id = A`, add the bilty, dispatch it back | Standard return flow |

---

## Frontend UI Checklist

### Challan List page

- [ ] Default tab: **My Challans** → calls `GET /v1/challan` (scoped to current branch automatically)
- [ ] Second tab: **Incoming** → calls `GET /v1/challan/incoming` (add endpoint per Part 3)
- [ ] Show `to_branch_id` label on every challan card so staff can tell where it is going
- [ ] Show `from_branch_id` label on incoming challan cards so staff can tell where it came from
- [ ] Badge "DISPATCHED", "ARRIVED_HUB" etc. in a colored chip

### Challan Settings page (for Branch B staff)

- [ ] When creating a Challan Book, expose **Route Scope** toggle: `OPEN` vs `FIXED_ROUTE`
- [ ] When `FIXED_ROUTE` is selected, show **From Branch** (auto-filled, read-only) and **To Branch** (dropdown of all company branches)
- [ ] API: `POST /v1/challan/book` with `route_scope: "FIXED_ROUTE"`, `from_branch_id`, `to_branch_id`

### Transfer single bilty UI (on Bilty detail page or context menu)

- [ ] Button: **"Send to Another Branch"** — visible only if bilty status is `SAVED` and has no `challan_id`
- [ ] On click: open a modal
  - Dropdown: **Destination Branch** (fetch all branches in company)
  - Auto-finds or creates an OPEN challan for the A→B route
  - Adds the bilty to the challan
  - Optional: immediately dispatch or just queue
- [ ] If bilty already has a `challan_id` — show which challan it is on and a "Remove from Challan" option before re-assigning

---

## API Quick Reference

| Action | Method | Endpoint |
|---|---|---|
| List my branch's challans | GET | `/v1/challan` |
| List incoming challans | GET | `/v1/challan/incoming` *(add per Part 3)* |
| Create dispatch challan | POST | `/v1/challan` |
| Add bilty to challan | POST | `/v1/challan/{id}/add-bilty` |
| Remove bilty from challan | POST | `/v1/challan/{id}/remove-bilty/{bilty_id}` |
| Dispatch challan | POST | `/v1/challan/{id}/dispatch` |
| Arrive hub (receive at branch) | POST | `/v1/challan/{id}/arrive-hub` |
| Find route book (B→A) | GET | `/v1/challan/book/by-route?from_branch_id=&to_branch_id=` |
| Create FIXED_ROUTE book | POST | `/v1/challan/book` |
| List available (SAVED) bilties | GET | `/v1/challan/available-bilties` |
| Save a draft bilty | PUT | `/v1/bilty/{id}` `{ "status": "SAVED" }` |
