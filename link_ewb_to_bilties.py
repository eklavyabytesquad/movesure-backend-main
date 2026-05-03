"""
link_ewb_to_bilties.py
Inserts ewb_records rows for the 10 test bilties so the frontend
can find EWBs linked to those bilties.
Run once then delete.
"""
from dotenv import load_dotenv; load_dotenv()
from app.services.utils.supabase import get_client

db = get_client()

COMPANY_ID = "815fcdb9-c36b-4288-9ed3-8210eaf40332"
BRANCH_ID  = "0c15b4c4-3d14-4c68-af43-c8ce7e738fd7"
CREATED_BY = "ab10fcbb-eb8e-434a-8272-ca1991bbfaed"

# bilty_id → ewb_number (dashes stripped to match NIC format)
BILTY_EWB = {
    "a6a0cf19-9600-4495-8dc5-0ef1d8bc9d18": "461719740647",   # 5527    → LUCKNOW
    "4817701e-204c-472e-9477-d00559567a9b": "401719413738",   # A10225  → KANPUR
    "3ca3e59c-c072-4b64-9e43-049ae26075f8": "441719850982",   # A10236  → MAHARAJ GANJ
    "509c9545-59ec-40c7-9c3c-9be17a030ed2": "481719855736",   # A10237  → PRAYAGRAJ
    "7bb68203-c745-41c9-91fa-aedd26a4b5c6": "451719079436",   # A10240  → PRAYAGRAJ
    "7b5230b6-bdb5-4890-b302-68fcc36b7517": "461719900829",   # A10243  → BANSI
    "54e66b8b-54dd-4fe5-b2f8-3f67447567bf": "461719118240",   # A10244  → KANPUR
    "f7c7ad7a-29b6-418f-a295-550aae2eb323": "491719549522",   # A10248  → SITAPUR
    "a775306a-d919-4106-8bab-3fbc2ee257c8": "411719764655",   # A10250  → PRATAPGARH
    "f0e4ab7b-5f05-4842-beca-8a053117440d": "411719918744",   # A10252  → (destination)
}

# Check which ewb_numbers already exist in ewb_records
existing = db.table("ewb_records").select("ewb_id,bilty_id,eway_bill_number") \
    .eq("company_id", COMPANY_ID).execute()
existing_by_ewb = {r["eway_bill_number"]: r for r in (existing.data or [])}
print(f"ewb_records found: {len(existing_by_ewb)}")

updated = 0
created = 0
for bilty_id, ewb_num in BILTY_EWB.items():
    if ewb_num in existing_by_ewb:
        row = existing_by_ewb[ewb_num]
        if row["bilty_id"] == bilty_id:
            print(f"  OK     ewb={ewb_num} already linked to correct bilty")
            continue
        # UPDATE bilty_id on the existing row
        res = db.table("ewb_records").update({
            "bilty_id":   bilty_id,
            "updated_by": CREATED_BY,
        }).eq("ewb_id", row["ewb_id"]).execute()
        if res.data:
            print(f"  UPDATE ewb={ewb_num} → bilty_id={bilty_id}")
            updated += 1
        else:
            print(f"  ERROR  updating ewb={ewb_num}: {res}")
    else:
        res = db.table("ewb_records").insert({
            "company_id":        COMPANY_ID,
            "branch_id":         BRANCH_ID,
            "bilty_id":          bilty_id,
            "eway_bill_number":  ewb_num,
            "ewb_status":        "ACTIVE",
            "generated_by_gstin": "07ABCPC0876F1Z1",
            "raw_response":      {},
            "created_by":        CREATED_BY,
            "updated_by":        CREATED_BY,
        }).execute()
        if res.data:
            print(f"  CREATE ewb={ewb_num} → bilty_id={bilty_id}")
            created += 1
        else:
            print(f"  ERROR  inserting ewb={ewb_num}: {res}")

print(f"\nDone — updated={updated} created={created}")
