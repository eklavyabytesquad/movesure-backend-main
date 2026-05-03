"""
Database operations for the E-Way Bill module.
All functions use the shared Supabase client.
Tables: ewb_records, ewb_validation_log, ewb_events, ewb_consolidated
"""
import logging
from typing import Any

from app.services.utils.supabase import get_client

logger = logging.getLogger("movesure.ewaybill.db")


# ─────────────────────────────────────────────────────────────────────────────
# ewb_records
# ─────────────────────────────────────────────────────────────────────────────

def get_ewb_record(company_id: str, eway_bill_number: str) -> dict | None:
    """Return existing ewb_record row or None."""
    db = get_client()
    res = (
        db.table("ewb_records")
        .select("*")
        .eq("company_id", company_id)
        .eq("eway_bill_number", str(eway_bill_number))
        .maybe_single()
        .execute()
    )
    return res.data if res.data else None


def get_ewbs_by_bilty(company_id: str, bilty_id: str) -> list[dict]:
    """Return all ewb_records linked to a bilty, newest first."""
    db = get_client()
    res = (
        db.table("ewb_records")
        .select("*")
        .eq("company_id", company_id)
        .eq("bilty_id", bilty_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def get_ewbs_by_challan(company_id: str, challan_id: str) -> list[dict]:
    """
    Return all ewb_records for a challan by joining through bilty.
    ewb_records.challan_id is not populated — bilties carry the challan_id.
    """
    db = get_client()
    # Step 1: get all bilty_ids in this challan
    bilties = (
        db.table("bilty")
        .select("bilty_id")
        .eq("company_id", company_id)
        .eq("challan_id", challan_id)
        .eq("is_active", True)
        .execute()
    )
    bilty_ids = [r["bilty_id"] for r in (bilties.data or [])]
    if not bilty_ids:
        return []
    # Step 2: fetch ewb_records for all those bilties
    res = (
        db.table("ewb_records")
        .select("*")
        .eq("company_id", company_id)
        .in_("bilty_id", bilty_ids)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def get_ewbs_by_challan_no(company_id: str, challan_no: str) -> list[dict]:
    """
    Same as get_ewbs_by_challan but accepts the human-readable challan number
    (e.g. 'A00003') instead of a UUID.
    """
    db = get_client()
    # Step 1: resolve challan_no → challan_id UUID
    challan = (
        db.table("challan")
        .select("challan_id")
        .eq("company_id", company_id)
        .eq("challan_no", challan_no)
        .limit(1)
        .execute()
    )
    if not challan.data:
        return []
    challan_id = challan.data[0]["challan_id"]
    return get_ewbs_by_challan(company_id, challan_id)


def get_all_validated_ewbs(company_id: str, branch_id: str | None = None) -> list[dict]:
    """Return all ewb_records for a company (optionally filtered by branch), newest first."""
    db = get_client()
    q = (
        db.table("ewb_records")
        .select("*")
        .eq("company_id", company_id)
        .order("created_at", desc=True)
    )
    if branch_id:
        q = q.eq("branch_id", branch_id)
    return q.execute().data or []


def upsert_ewb_record(
    *,
    company_id: str,
    branch_id: str,
    eway_bill_number: str,
    ewb_status: str,
    raw_response: dict,
    created_by: str,
    # optional fields
    bilty_id: str | None = None,
    challan_id: str | None = None,
    cewb_id: str | None = None,
    document_number: str | None = None,
    document_date: str | None = None,
    document_type: str | None = None,
    generated_by_gstin: str | None = None,
    gstin_of_consignor: str | None = None,
    gstin_of_consignee: str | None = None,
    transporter_id: str | None = None,
    transporter_name: str | None = None,
    vehicle_number: str | None = None,
    vehicle_type: str | None = None,
    state_of_consignor: str | None = None,
    state_of_supply: str | None = None,
    consignor_name: str | None = None,
    pincode_of_consignor: str | None = None,
    consignee_name: str | None = None,
    pincode_of_consignee: str | None = None,
    eway_bill_date: str | None = None,
    valid_upto: str | None = None,
    items_json: list[dict] | None = None,
    is_self_transfer: bool = False,
    total_invoice_value: float | None = None,
    taxable_amount: float | None = None,
    supply_type: str | None = None,
    sub_supply_type: str | None = None,
    transportation_mode: str | None = None,
    transportation_distance: int | None = None,
) -> dict:
    """Upsert a record into ewb_records (conflict on company_id + eway_bill_number)."""
    db = get_client()

    row: dict[str, Any] = {
        "company_id":          company_id,
        "branch_id":           branch_id,
        "eway_bill_number":    str(eway_bill_number),
        "ewb_status":          ewb_status,
        "raw_response":        raw_response,
        "created_by":          created_by,
        "is_self_transfer":    is_self_transfer,
    }
    # optional fields — only include if provided (use actual DB column names)
    optional = {
        "bilty_id":              bilty_id,
        "challan_id":            challan_id,
        "cewb_id":               cewb_id,
        "document_number":       document_number,
        "document_date":         document_date,
        "document_type":         document_type,
        "generated_by_gstin":    generated_by_gstin,
        "gstin_of_consignor":    gstin_of_consignor,
        "consignor_name":        consignor_name,
        "pincode_of_consignor":  pincode_of_consignor,
        "gstin_of_consignee":    gstin_of_consignee,
        "consignee_name":        consignee_name,
        "pincode_of_consignee":  pincode_of_consignee,
        "transporter_id":        transporter_id,
        "transporter_name":      transporter_name,
        "vehicle_number":        vehicle_number,
        "vehicle_type":          vehicle_type,
        "state_of_consignor":    state_of_consignor,
        "state_of_supply":       state_of_supply,
        "eway_bill_date":        eway_bill_date,
        "valid_upto":            valid_upto,
        "items_json":            items_json,
        "total_invoice_value":   total_invoice_value,
        "taxable_amount":        taxable_amount,
        "supply_type":           supply_type,
        "sub_supply_type":       sub_supply_type,
        "transportation_mode":   transportation_mode,
        "transportation_distance": transportation_distance,
    }
    for k, v in optional.items():
        if v is not None:
            row[k] = v

    res = (
        db.table("ewb_records")
        .upsert(row, on_conflict="company_id,eway_bill_number")
        .execute()
    )
    if not res.data:
        logger.warning("upsert_ewb_record returned empty | ewb=%s", eway_bill_number)
        return row
    return res.data[0]


def update_ewb_record_fields(
    *,
    company_id: str,
    eway_bill_number: str,
    updates: dict,
) -> None:
    """Patch specific columns on an ewb_records row."""
    db = get_client()
    (
        db.table("ewb_records")
        .update(updates)
        .eq("company_id", company_id)
        .eq("eway_bill_number", str(eway_bill_number))
        .execute()
    )


# ─────────────────────────────────────────────────────────────────────────────
# ewb_validation_log
# ─────────────────────────────────────────────────────────────────────────────

def _next_version_no(db, ewb_id: str) -> int:
    """SELECT MAX(version_no)+1 for the given ewb_id."""
    res = (
        db.table("ewb_validation_log")
        .select("version_no")
        .eq("ewb_id", ewb_id)
        .order("version_no", desc=True)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]["version_no"] + 1
    return 1


# Valid triggered_by values — must match DB CHECK constraint in ewaybill.sql
_VALID_TRIGGERED_BY = {"manual", "auto", "on_generate", "on_bilty_save"}


def insert_validation_log(
    *,
    ewb_id: str,
    eway_bill_number: str,
    nic_response: dict,
    company_id: str,
    branch_id: str,
    created_by: str,
    triggered_by: str = "manual",
) -> dict:
    """Append a versioned NIC snapshot to ewb_validation_log."""
    db = get_client()
    version_no = _next_version_no(db, ewb_id)

    # Normalise triggered_by to a valid DB enum value
    if triggered_by not in _VALID_TRIGGERED_BY:
        triggered_by = "manual"

    results = nic_response.get("results", {})
    msg = results.get("message", {}) if isinstance(results.get("message"), dict) else {}

    # Detect NIC-level error embedded in the response
    error_info = results.get("error") or {}
    error_code = str(error_info.get("errorCodes", "") or "") or None
    error_desc = str(error_info.get("message", "") or "") or None

    def _get(msg, *keys):
        for k in keys:
            v = msg.get(k) if msg else None
            if v is not None and v != "":
                return v
        return None

    row: dict[str, Any] = {
        "ewb_id":             ewb_id,
        "eway_bill_number":   str(eway_bill_number),
        "version_no":         version_no,
        "nic_status":         _get(msg, "status", "eway_bill_status"),
        "valid_upto":         _get(msg, "ewbValidTill", "eway_bill_valid_date"),
        "generated_by_gstin": _get(msg, "genGstin", "userGstin"),
        "vehicle_number":     _get(msg, "vehicleNo", "vehicle_number"),
        "transporter_id":     _get(msg, "transporterId", "transporter_id"),
        "error_code":         error_code,
        "error_description":  error_desc,
        "triggered_by":       triggered_by,
        "raw_response":       nic_response,
        "company_id":         company_id,
        "branch_id":          branch_id,
        "created_by":         created_by,
    }
    # Strip None values so DB defaults apply cleanly
    row = {k: v for k, v in row.items() if v is not None or k in
           ("ewb_id", "eway_bill_number", "version_no", "raw_response",
            "company_id", "branch_id", "created_by")}

    res = db.table("ewb_validation_log").insert(row).execute()
    return res.data[0] if res.data else row


# ─────────────────────────────────────────────────────────────────────────────
# ewb_validation_log — read
# ─────────────────────────────────────────────────────────────────────────────

def get_validation_history(
    company_id: str,
    eway_bill_number: str,
    *,
    limit: int = 100,
) -> list[dict]:
    """
    Return all ewb_validation_log rows for the given EWB number, newest first.
    Since eway_bill_number + company_id are denormalised on the log table
    we can query directly without joining ewb_records.
    """
    db = get_client()
    res = (
        db.table("ewb_validation_log")
        .select(
            "log_id, ewb_id, eway_bill_number, version_no, nic_status, "
            "valid_upto, generated_by_gstin, vehicle_number, transporter_id, "
            "error_code, error_description, triggered_by, validated_at, created_by"
        )
        .eq("company_id", company_id)
        .eq("eway_bill_number", str(eway_bill_number))
        .order("version_no", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


# ─────────────────────────────────────────────────────────────────────────────
# ewb_events
# ─────────────────────────────────────────────────────────────────────────────

def insert_event(
    *,
    ewb_id: str,
    eway_bill_number: str,
    event_type: str,
    company_id: str,
    branch_id: str,
    created_by: str,
    event_data: dict | None = None,
    raw_response: dict | None = None,
    reference_id: str | None = None,
    notes: str | None = None,
) -> dict:
    """Append an event row to ewb_events (always INSERT, never UPDATE)."""
    db = get_client()
    row: dict[str, Any] = {
        "ewb_id":           ewb_id,
        "eway_bill_number": str(eway_bill_number),
        "event_type":       event_type,
        "company_id":       company_id,
        "branch_id":        branch_id,
        "created_by":       created_by,
    }
    if event_data:
        row["event_data"] = event_data
    if raw_response:
        row["raw_response"] = raw_response
    if reference_id:
        row["reference_id"] = reference_id
    if notes:
        row["notes"] = notes

    res = db.table("ewb_events").insert(row).execute()
    return res.data[0] if res.data else row


# ─────────────────────────────────────────────────────────────────────────────
# ewb_consolidated
# ─────────────────────────────────────────────────────────────────────────────

def _normalise_pdf_url(url: str | None) -> str | None:
    if not url:
        return url
    return url if url.startswith("http") else "https://" + url


def save_consolidated(
    *,
    company_id: str,
    branch_id: str,
    cewb_number: str,
    cewb_date: str | None,
    vehicle_number: str | None,
    place_of_consignor: str | None,
    state_of_consignor: str | None,
    mode_of_transport: str | None,
    transporter_doc_number: str | None,
    transporter_doc_date: str | None,
    ewb_numbers: list[str],
    raw_response: dict,
    created_by: str,
    pdf_url: str | None = None,
    trip_sheet_id: str | None = None,
) -> dict:
    """Insert a row into ewb_consolidated."""
    db = get_client()
    row: dict[str, Any] = {
        "company_id":             company_id,
        "branch_id":              branch_id,
        "cewb_number":            cewb_number,
        "cewb_date":              cewb_date,
        "vehicle_number":         vehicle_number or "",
        "place_of_consignor":     place_of_consignor or "",
        "state_of_consignor":     state_of_consignor or "",
        "mode_of_transport":      str(mode_of_transport) if mode_of_transport is not None else "1",
        "transporter_doc_number": transporter_doc_number or "",
        "transporter_doc_date":   transporter_doc_date or "",
        "ewb_numbers":            ewb_numbers,
        "pdf_url":                _normalise_pdf_url(pdf_url),
        "raw_response":           raw_response,
        "created_by":             created_by,
    }
    if trip_sheet_id:
        row["trip_sheet_id"] = trip_sheet_id
    res = db.table("ewb_consolidated").insert(row).execute()
    return res.data[0] if res.data else row


def get_cewbs_by_trip(company_id: str, trip_sheet_id: str) -> list[dict]:
    """Return all consolidated EWBs for a trip sheet, newest first."""
    db = get_client()
    res = (
        db.table("ewb_consolidated")
        .select("*")
        .eq("company_id", company_id)
        .eq("trip_sheet_id", trip_sheet_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def link_ewbs_to_cewb(cewb_id: str, ewb_numbers: list[str], company_id: str) -> None:
    """Set cewb_id on all member ewb_records rows."""
    if not ewb_numbers:
        return
    db = get_client()
    (
        db.table("ewb_records")
        .update({"cewb_id": cewb_id})
        .eq("company_id", company_id)
        .in_("eway_bill_number", ewb_numbers)
        .execute()
    )
