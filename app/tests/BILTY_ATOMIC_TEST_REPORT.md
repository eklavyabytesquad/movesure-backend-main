# Bilty Atomic GR Number — Concurrency Test Report

**Run date:** 2026-04-27T02:30:31Z  
**Environment:** `http://localhost:8000/v1`  
**Company:** `815fcdb9-c36b-4288-9ed3-8210eaf40332`  
**Branch:** `0c15b4c4-3d14-4c68-af43-c8ce7e738fd7`  
**Result: 17 / 17 PASSED ✓**

---

## What Was Tested

The test verifies that the `fn_next_gr_no()` PostgreSQL function correctly prevents duplicate GR numbers when multiple requests arrive simultaneously — a real-world scenario when two staff members create bilties at the same time.

### Why duplicates would be a problem without the lock

Without atomicity, the sequence:

```
Request A → reads current_number = 5
Request B → reads current_number = 5   ← same value!
Request A → writes GR "TST/0005", increments to 6
Request B → writes GR "TST/0005"       ← DUPLICATE!
```

Both bilties would get the same GR number, causing a `UNIQUE` constraint violation or — worse — silently conflicting records.

### How `fn_next_gr_no()` prevents this

The function uses `SELECT ... FOR UPDATE` to lock the `bilty_book` row for the duration of the transaction:

```sql
SELECT current_number, to_number, ...
FROM   bilty_book
WHERE  book_id = p_book_id
FOR UPDATE;   ← row is locked
```

Any second concurrent call to the same `book_id` **blocks** at this line until the first transaction commits and releases the lock. This guarantees the sequence:

```
Request A → locks row, reads 5, writes GR "TST/0005", increments to 6, releases lock
Request B → unblocks, reads 6, writes GR "TST/0006", increments to 7, releases lock
```

No duplicates. No reservation table. No application-level locking needed.

---

## Test Setup

| Item | Value |
|---|---|
| Book | `9c8e1949-c616-4f4d-995b-1508c989d232` |
| Book name | `AtomicTest-Book-*` |
| Type | `REGULAR`, `COMMON` scope |
| Range | 1 – 100, prefix `TST/`, 4 digits |
| Consignors | Sharma Traders, Patel Enterprises |
| Consignees | Delhi Distributors, Chennai Clearing |

---

## Results

### Setup (5 checks)

| # | Check | Result |
|---|---|---|
| 1 | Create bilty book | ✓ PASS |
| 2 | Create consignor: Sharma Traders | ✓ PASS |
| 3 | Create consignor: Patel Enterprises | ✓ PASS |
| 4 | Create consignee: Delhi Distributors | ✓ PASS |
| 5 | Create consignee: Chennai Clearing | ✓ PASS |

---

### Round 1 — 3 Concurrent Requests (6 checks)

3 requests fired simultaneously to `GET /v1/bilty/next-gr/{book_id}`.

| # | Check | Result | Detail |
|---|---|---|---|
| 6 | 3 GR claims → all 3 returned | ✓ PASS | 3 valid responses |
| 7 | GR strings unique (no duplicates) | ✓ PASS | `['TST/0001', 'TST/0002', 'TST/0003']` |
| 8 | GR integers unique (no duplicates) | ✓ PASS | `[1, 2, 3]` |
| 9 | No errors on GR claim | ✓ PASS | |
| 10 | All 3 bilties created (status 201) | ✓ PASS | created=3 failed=0 |
| 11 | Bilty GR strings unique | ✓ PASS | unique=3 |

**GR claim time:** 383 ms for 3 concurrent requests  
**Bilty insert time:** 372 ms for 3 concurrent inserts

The 3 requests arrived simultaneously but each received a **strictly sequential, non-overlapping** GR number: `TST/0001`, `TST/0002`, `TST/0003`.

---

### Round 2 — 6 Concurrent Requests (6 checks)

6 requests fired simultaneously to `GET /v1/bilty/next-gr/{book_id}`.

| # | Check | Result | Detail |
|---|---|---|---|
| 12 | 6 GR claims → all 6 returned | ✓ PASS | 6 valid responses |
| 13 | GR strings unique (no duplicates) | ✓ PASS | `['TST/0004' … 'TST/0009']` |
| 14 | GR integers unique (no duplicates) | ✓ PASS | `[4, 5, 6, 7, 8, 9]` |
| 15 | No errors on GR claim | ✓ PASS | |
| 16 | All 6 bilties created (status 201) | ✓ PASS | created=6 failed=0 |
| 17 | Bilty GR strings unique | ✓ PASS | unique=6 |

**GR claim time:** 408 ms for 6 concurrent requests  
**Bilty insert time:** 420 ms for 6 concurrent inserts

Note that the 6 GR numbers came back **out of order** from the caller's perspective (`TST/0004, TST/0009, TST/0007, TST/0005, TST/0008, TST/0006`) — this is expected. The HTTP responses return in the order they complete, but the actual GR integers (`4, 5, 6, 7, 8, 9`) are a complete, gapless, duplicate-free set. The DB serialised access perfectly.

---

## Summary

```
Total checks : 17
Passed       : 17
Failed       :  0
```

**The atomic GR generation is working correctly.** Under both 3-concurrent and 6-concurrent load:

- Zero duplicate GR numbers were issued
- Zero errors were returned
- All bilties were successfully created
- The `current_number` counter in `bilty_book` advanced correctly from 1 → 9 across both rounds
- Out-of-order HTTP response arrival is normal and expected; only the DB values matter

---

## How to Re-run

```powershell
# With a token
$env:TOKEN="<your_jwt>"; python app/tests/test_bilty_atomic.py

# With credentials (auto-login)
$env:LOGIN_EMAIL="your@email.com"; $env:LOGIN_PASSWORD="YourPass"; python app/tests/test_bilty_atomic.py
```

Results are saved to `app/tests/test_bilty_atomic_results.json` after each run.

---

## Files

| File | Purpose |
|---|---|
| `app/tests/test_bilty_atomic.py` | Test script — setup + concurrent rounds |
| `app/tests/test_bilty_atomic_results.json` | Last run results (auto-generated) |
