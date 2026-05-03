"""
seed_test_bilties.py
Inserts 10 test bilties with EWB numbers for testing.
Run: python seed_test_bilties.py
"""
import uuid
from datetime import date
from dotenv import load_dotenv
load_dotenv()

from app.services.utils.supabase import get_client

db = get_client()

# ── Config from attached SQL ──────────────────────────────────
COMPANY_ID   = "815fcdb9-c36b-4288-9ed3-8210eaf40332"
BRANCH_ID    = "0c15b4c4-3d14-4c68-af43-c8ce7e738fd7"
CREATED_BY   = "ab10fcbb-eb8e-434a-8272-ca1991bbfaed"
BOOK_ID      = "9c8e1949-c616-4f4d-995b-1508c989d232"
FROM_CITY_ID = "0fb3a1fd-933b-46fa-b7d8-1bab7a99e43d"  # KANPUR
CONSIGNOR_ID   = "d9896268-f070-4e07-9040-6ef7ae5c2a8b"
CONSIGNOR_NAME = "Patel Enterprises"
CONSIGNEE_ID   = "0c5f9614-d3e1-437c-aa63-453b4a0d870e"
CONSIGNEE_NAME = "RAJ ENT.P"
TRANSPORT_ID   = "3be455ff-997d-4324-b322-7dad13fa892e"
TRANSPORT_NAME = "SS TRANSPORT CORPORATION"
TRANSPORT_GSTIN = "09COVPS5556J1ZT"

TODAY = "2026-05-03"

# ── EWB data: (gr_no, ewb_number, destination_city_name) ─────
BILTIES = [
    ("5527",   "461719740647", "LUCKNOW"),
    ("A10225", "401719413738", "KANPUR"),
    ("A10236", "441719850982", "MAHARAJGANJ"),
    ("A10237", "481719855736", "PRAYAGRAJ"),
    ("A10240", "451719079436", "PRAYAGRAJ"),
    ("A10243", "461719900829", "BANSI"),
    ("A10244", "461719118240", "KANPUR"),
    ("A10248", "491719549522", "SITAPUR"),
    ("A10250", "411719764655", "PRATAPGARH"),
    ("A10252", "411719918744", "KANPUR"),
]

# ── Fetch city IDs for all destination cities ─────────────────
dest_city_names = list({b[2] for b in BILTIES})
print("Fetching city IDs for:", dest_city_names)

city_res = (
    db.table("master_city")
    .select("city_id,city_name,city_code")
    .eq("company_id", COMPANY_ID)
    .eq("branch_id", BRANCH_ID)
    .execute()
)

# Build name→id map (case-insensitive, partial match)
city_map = {}
for c in (city_res.data or []):
    city_map[c["city_name"].upper()] = c["city_id"]

# Resolve destination city IDs (partial match fallback)
def resolve_city(name: str) -> str | None:
    upper = name.upper()
    if upper in city_map:
        return city_map[upper]
    # partial
    for k, v in city_map.items():
        if upper in k or k in upper:
            print(f"  Partial match: '{name}' → '{k}'")
            return v
    return None

print(f"Total cities in DB: {len(city_map)}")

# ── Insert bilties ────────────────────────────────────────────
created = 0
errors  = 0

for gr_no, ewb_no, dest_city in BILTIES:
    to_city_id = resolve_city(dest_city)
    if not to_city_id:
        print(f"  SKIP {gr_no}: city '{dest_city}' not found in master_city")
        errors += 1
        continue

    bilty_id = str(uuid.uuid4())
    fmt = f"{ewb_no[:4]}-{ewb_no[4:8]}-{ewb_no[8:]}" if len(ewb_no) == 12 else ewb_no
    e_way_bills = [{"ewb_no": fmt}]

    row = {
        "bilty_id":         bilty_id,
        "company_id":       COMPANY_ID,
        "branch_id":        BRANCH_ID,
        "gr_no":            gr_no,
        "book_id":          BOOK_ID,
        "bilty_type":       "REGULAR",
        "bilty_date":       TODAY,
        "consignor_id":     CONSIGNOR_ID,
        "consignor_name":   CONSIGNOR_NAME,
        "consignor_gstin":  "21AABCS12341Z5",
        "consignor_mobile": "91000000001",
        "consignee_id":     CONSIGNEE_ID,
        "consignee_name":   CONSIGNEE_NAME,
        "consignee_mobile": "7987984844",
        "transport_id":     TRANSPORT_ID,
        "transport_name":   TRANSPORT_NAME,
        "transport_gstin":  TRANSPORT_GSTIN,
        "from_city_id":     FROM_CITY_ID,
        "to_city_id":       to_city_id,
        "delivery_type":    "DOOR",
        "payment_mode":     "PAID",
        "e_way_bills":      e_way_bills,
        "no_of_pkg":        "1",
        "freight_amount":   "0.0",
        "total_amount":     "0.0",
        "saving_option":    "SAVE",
        "status":           "SAVED",
        "is_dispatched":    False,
        "is_reached_hub":   False,
        "is_at_godown":     False,
        "is_out_for_delivery": False,
        "is_delivered":     False,
        "is_active":        True,
        "tracking_meta":    {},
        "metadata":         {},
        "created_by":       CREATED_BY,
        "updated_by":       CREATED_BY,
        "labour_charge":    "0.0",
        "bill_charge":      "0.0",
        "toll_charge":      "0.0",
        "dd_charge":        "0.0",
        "pf_charge":        "0.0",
        "other_charge":     "0.0",
        "local_charge":     "0",
        "discount_amount":  "0",
        "discount_percentage": "0",
        "kaat_rate":        "0",
        "kaat_weight_charged": "0",
        "kaat_base_amount": "0",
        "kaat_receiving_slip_charge": "0",
        "kaat_bilty_charge": "0",
        "kaat_labour_charge": "0",
        "kaat_other_charges_total": "0",
        "kaat_amount":      "0",
        "real_dd_charge":   "0",
        "transit_profit":   "0",
    }

    res = db.table("bilty").insert(row).execute()
    if res.data:
        print(f"  CREATED gr={gr_no} ewb={ewb_no} → {dest_city} [{bilty_id[:8]}]")
        created += 1
    else:
        print(f"  ERROR gr={gr_no}: {res}")
        errors += 1

print(f"\nDone — created: {created}, errors: {errors}")
