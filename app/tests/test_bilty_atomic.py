"""
Bilty Atomic GR Number Test Suite
===================================
Tests concurrent bilty creation to verify the DB-level FOR UPDATE lock in
fn_next_gr_no() prevents duplicate GR numbers under parallel load.

Usage
-----
  python app/tests/test_bilty_atomic.py

Prerequisites
-------------
  1. Server running at BASE_URL (default http://localhost:8000)
  2. httpx installed:  pip install httpx
  3. Fill in TOKEN (get from POST /v1/auth/login) or set LOGIN_EMAIL/LOGIN_PASSWORD env vars.

The script:
  1. Logs in (if TOKEN is empty) to get a JWT
  2. Creates a bilty_book (REGULAR, COMMON, 1-100)
  3. Creates 2 consignors + 2 consignees
  4. ROUND 1 — 3 concurrent bilty creations → expects 3 unique GR numbers
  5. ROUND 2 — 6 concurrent bilty creations → expects 6 unique GR numbers
  6. Prints a full pass/fail report
"""

import asyncio
import json
import os
import sys
import time
from datetime import date

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000/v1")

# Hard-code a token here OR set LOGIN_EMAIL + LOGIN_PASSWORD env vars
TOKEN = os.getenv("TOKEN", "")

LOGIN_EMAIL    = os.getenv("LOGIN_EMAIL", "")
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "")

# IDs from the request
USER_ID    = "c2adecc3-f8d0-4baf-befd-1345f2597e04"
COMPANY_ID = "815fcdb9-c36b-4288-9ed3-8210eaf40332"
BRANCH_ID  = "0c15b4c4-3d14-4c68-af43-c8ce7e738fd7"

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

# ── Helpers ───────────────────────────────────────────────────────────────────
_results: list[dict] = []


def log(label: str, passed: bool, detail: str = ""):
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  {status}  {label}")
    if detail:
        print(f"         {detail}")
    _results.append({"label": label, "passed": passed, "detail": detail})


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ── Step 0: Login ─────────────────────────────────────────────────────────────
def get_token() -> str:
    global TOKEN
    if TOKEN:
        print(f"\n[0] Using provided token (first 20 chars): {TOKEN[:20]}...")
        return TOKEN
    if not LOGIN_EMAIL or not LOGIN_PASSWORD:
        print("\nERROR: Provide TOKEN or set LOGIN_EMAIL + LOGIN_PASSWORD env vars.")
        sys.exit(1)
    print(f"\n[0] Logging in as {LOGIN_EMAIL} ...")
    r = httpx.post(f"{BASE_URL}/auth/login", json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD})
    r.raise_for_status()
    TOKEN = r.json()["access_token"]
    print(f"    Token obtained: {TOKEN[:20]}...")
    return TOKEN


# ── Step 1: Create bilty book ─────────────────────────────────────────────────
def create_book(token: str) -> str:
    print("\n[1] Creating bilty book (REGULAR, COMMON, range 1-100) ...")
    payload = {
        "book_name":    f"AtomicTest-Book-{int(time.time())}",
        "bilty_type":   "REGULAR",
        "party_scope":  "COMMON",
        "prefix":       "TST/",
        "from_number":  1,
        "to_number":    100,
        "digits":       4,
        "postfix":      "",
        "is_fixed":     False,
        "auto_continue": False,
    }
    r = httpx.post(f"{BASE_URL}/bilty-setting/books", json=payload, headers=headers(token))
    ok = r.status_code == 201
    log("Create bilty book", ok, f"status={r.status_code}" if not ok else f"book_id={r.json()['book']['book_id']}")
    if not ok:
        print(f"    Response: {r.text}")
        sys.exit(1)
    book_id = r.json()["book"]["book_id"]
    print(f"    book_id: {book_id}")
    return book_id


# ── Step 2: Create consignors ─────────────────────────────────────────────────
def create_consignors(token: str) -> list[dict]:
    print("\n[2] Creating consignors ...")
    consignors = []
    names = ["Sharma Traders", "Patel Enterprises"]
    for i, name in enumerate(names):
        payload = {
            "consignor_name": name,
            "gstin":  f"2{i}AABCS1234{i}Z5",
            "mobile": f"9{i}00000000{i}",
            "city":   "Mumbai",
            "state":  "Maharashtra",
        }
        r = httpx.post(f"{BASE_URL}/bilty-setting/consignors", json=payload, headers=headers(token))
        ok = r.status_code == 201
        log(f"Create consignor: {name}", ok, f"status={r.status_code}" if not ok else "")
        if ok:
            c = r.json()["consignor"]
            consignors.append(c)
            print(f"    consignor_id: {c['consignor_id']}  name: {c['consignor_name']}")
    return consignors


# ── Step 3: Create consignees ─────────────────────────────────────────────────
def create_consignees(token: str) -> list[dict]:
    print("\n[3] Creating consignees ...")
    consignees = []
    names = ["Delhi Distributors", "Chennai Clearing"]
    for i, name in enumerate(names):
        payload = {
            "consignee_name": name,
            "mobile": f"8{i}00000001{i}",
            "city":   "Delhi",
            "state":  "Delhi",
        }
        r = httpx.post(f"{BASE_URL}/bilty-setting/consignees", json=payload, headers=headers(token))
        ok = r.status_code == 201
        log(f"Create consignee: {name}", ok, f"status={r.status_code}" if not ok else "")
        if ok:
            c = r.json()["consignee"]
            consignees.append(c)
            print(f"    consignee_id: {c['consignee_id']}  name: {c['consignee_name']}")
    return consignees


# ── Step 4: Next GR helper ─────────────────────────────────────────────────────
async def fetch_next_gr(client: httpx.AsyncClient, token: str, book_id: str) -> dict | None:
    try:
        r = await client.get(f"{BASE_URL}/bilty/next-gr/{book_id}", headers=headers(token))
        if r.status_code == 200:
            return r.json()
        return {"error": r.text, "status": r.status_code}
    except Exception as exc:
        return {"error": str(exc)}


# ── Step 5: Create bilty helper ────────────────────────────────────────────────
async def create_bilty_async(
    client: httpx.AsyncClient,
    token: str,
    book_id: str,
    gr_info: dict,
    consignor: dict,
    consignee: dict,
    idx: int,
) -> dict:
    payload = {
        "gr_no":           gr_info["gr_no"],
        "book_id":         book_id,
        "bilty_type":      "REGULAR",
        "bilty_date":      str(date.today()),
        "consignor_id":    consignor["consignor_id"],
        "consignor_name":  consignor["consignor_name"],
        "consignor_gstin": consignor.get("gstin"),
        "consignor_mobile": consignor.get("mobile"),
        "consignee_id":    consignee["consignee_id"],
        "consignee_name":  consignee["consignee_name"],
        "consignee_mobile": consignee.get("mobile"),
        "payment_mode":    "PAID",
        "delivery_type":   "DOOR",
        "no_of_pkg":       idx + 1,
        "weight":          (idx + 1) * 10.5,
        "total_amount":    (idx + 1) * 500.0,
        "saving_option":   "SAVE",
        "status":          "SAVED",
        "remark":          f"Concurrent test bilty #{idx + 1}",
    }
    try:
        r = await client.post(f"{BASE_URL}/bilty", json=payload, headers=headers(token))
        return {
            "idx":     idx,
            "status":  r.status_code,
            "gr_no":   gr_info["gr_no"],
            "gr_num":  gr_info["gr_number"],
            "bilty_id": r.json().get("bilty", {}).get("bilty_id") if r.status_code == 201 else None,
            "error":   r.text if r.status_code != 201 else None,
        }
    except Exception as exc:
        return {"idx": idx, "status": 0, "gr_no": gr_info["gr_no"], "gr_num": gr_info["gr_number"], "error": str(exc)}


# ── Concurrent round ───────────────────────────────────────────────────────────
async def run_concurrent_round(
    label: str,
    token: str,
    book_id: str,
    consignors: list,
    consignees: list,
    n: int,
) -> list[dict]:
    print(f"\n[{label}] Firing {n} concurrent GET /bilty/next-gr ...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step A — claim N GR numbers concurrently
        gr_tasks = [fetch_next_gr(client, token, book_id) for _ in range(n)]
        t0 = time.perf_counter()
        gr_results = await asyncio.gather(*gr_tasks)
        elapsed_gr = (time.perf_counter() - t0) * 1000

    print(f"    GR claims completed in {elapsed_gr:.0f} ms")
    print(f"    GR numbers claimed: {[r.get('gr_no') for r in gr_results]}")

    # Check uniqueness
    gr_nos   = [r.get("gr_no")   for r in gr_results if r and "gr_no"   in r]
    gr_nums  = [r.get("gr_number") for r in gr_results if r and "gr_number" in r]
    errors   = [r for r in gr_results if r and "error" in r]

    unique_nos  = len(set(gr_nos))
    unique_nums = len(set(gr_nums))

    log(f"{label}: {n} GR claims → all {n} returned",       len(gr_nos) == n,  f"got {len(gr_nos)} valid responses")
    log(f"{label}: GR strings unique (no duplicates)",       unique_nos == n,   f"unique={unique_nos} / expected={n}  values={sorted(gr_nos)}")
    log(f"{label}: GR integers unique (no duplicates)",      unique_nums == n,  f"unique={unique_nums} / expected={n} values={sorted(gr_nums)}")
    log(f"{label}: No errors on GR claim",                   len(errors) == 0,  f"errors={errors}" if errors else "")

    # Step B — create bilties for each claimed GR
    print(f"    Creating {n} bilties ...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        bilty_tasks = [
            create_bilty_async(
                client, token, book_id,
                gr_results[i],
                consignors[i % len(consignors)],
                consignees[i % len(consignees)],
                i,
            )
            for i in range(n) if "gr_no" in gr_results[i]
        ]
        t1 = time.perf_counter()
        bilty_results = await asyncio.gather(*bilty_tasks)
        elapsed_bilty = (time.perf_counter() - t1) * 1000

    print(f"    Bilty inserts completed in {elapsed_bilty:.0f} ms")

    created    = [b for b in bilty_results if b["status"] == 201]
    failed     = [b for b in bilty_results if b["status"] != 201]
    bilty_gr   = [b["gr_no"] for b in created]
    unique_bgr = len(set(bilty_gr))

    log(f"{label}: All {n} bilties created (status 201)",    len(created) == n,   f"created={len(created)} failed={len(failed)}")
    log(f"{label}: Bilty GR strings unique",                 unique_bgr == len(created), f"unique={unique_bgr}")
    if failed:
        for f in failed:
            print(f"      FAILED bilty idx={f['idx']} gr={f['gr_no']} error={f['error']}")

    return bilty_results


# ── Main ───────────────────────────────────────────────────────────────────────
async def main():
    print("=" * 60)
    print("  Bilty Atomic GR Number — Concurrency Test")
    print(f"  Target: {BASE_URL}")
    print(f"  Company: {COMPANY_ID}")
    print(f"  Branch:  {BRANCH_ID}")
    print("=" * 60)

    token       = get_token()
    book_id     = create_book(token)
    consignors  = create_consignors(token)
    consignees  = create_consignees(token)

    if not consignors or not consignees:
        print("\nERROR: Could not create consignors/consignees — aborting bilty tests.")
        sys.exit(1)

    # Round 1 — 3 concurrent
    await run_concurrent_round("Round-1 (3 concurrent)", token, book_id, consignors, consignees, 3)

    # Round 2 — 6 concurrent
    await run_concurrent_round("Round-2 (6 concurrent)", token, book_id, consignors, consignees, 6)

    # ── Summary ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  RESULTS SUMMARY")
    print("=" * 60)
    passed = [r for r in _results if r["passed"]]
    failed = [r for r in _results if not r["passed"]]
    for r in _results:
        mark = "✓" if r["passed"] else "✗"
        print(f"  {mark}  {r['label']}")
        if r["detail"] and not r["passed"]:
            print(f"       → {r['detail']}")
    print()
    print(f"  Total: {len(_results)}  Passed: {len(passed)}  Failed: {len(failed)}")
    if failed:
        print(f"\n  FAILED CHECKS:")
        for r in failed:
            print(f"    • {r['label']}: {r['detail']}")
    print("=" * 60)

    # Write results to a JSON file for the README
    out = {
        "timestamp":  time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url":   BASE_URL,
        "company_id": COMPANY_ID,
        "branch_id":  BRANCH_ID,
        "total":      len(_results),
        "passed":     len(passed),
        "failed":     len(failed),
        "checks":     _results,
    }
    result_path = os.path.join(os.path.dirname(__file__), "test_bilty_atomic_results.json")
    with open(result_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n  Results saved → {result_path}")

    return 0 if not failed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
