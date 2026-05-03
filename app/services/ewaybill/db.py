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
    doc_number: str | None = None,
    doc_date: str | None = None,
    doc_type: str | None = None,
    gstin_of_generator: str | None = None,
    gstin_of_consignor: str | None = None,
    gstin_of_consignee: str | None = None,
    transporter_id: str | None = None,
    transporter_name: str | None = None,
    vehicle_number: str | None = None,
    from_state: str | None = None,
    to_state: str | None = None,
    from_pincode: str | None = None,
    to_pincode: str | None = None,
    ewb_date: str | None = None,
    valid_upto: str | None = None,
    items_json: list[dict] | None = None,
    is_self_transfer: bool = False,
    total_value: float | None = None,
    supply_type: str | None = None,
    transport_mode: str | None = None,
    transport_distance: int | None = None,
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
    # optional fields — only include if provided
    optional = {
        "bilty_id": bilty_id,
        "challan_id": challan_id,
        "cewb_id": cewb_id,
        "doc_number": doc_number,
        "doc_date": doc_date,
        "doc_type": doc_type,
        "gstin_of_generator": gstin_of_generator,
        "gstin_of_consignor": gstin_of_consignor,
        "gstin_of_consignee": gstin_of_consignee,
        "transporter_id": transporter_id,
        "transporter_name": transporter_name,
        "vehicle_number": vehicle_number,
        "from_state": from_state,
        "to_state": to_state,
        "from_pincode": from_pincode,
        "to_pincode": to_pincode,
        "ewb_date": ewb_date,
        "valid_upto": valid_upto,
        "items_json": items_json,
        "total_value": total_value,
        "supply_type": supply_type,
        "transport_mode": transport_mode,
        "transport_distance": transport_distance,
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

    row: dict[str, Any] = {
        "ewb_id":             ewb_id,
        "eway_bill_number":   str(eway_bill_number),
        "version_no":         version_no,
        # nic_status mirrors the NIC-returned status field
        "nic_status":         msg.get("status") if msg else None,
        "valid_upto":         msg.get("ewbValidTill") if msg else None,
        "generated_by_gstin": msg.get("genGstin") if msg else None,
        "vehicle_number":     msg.get("vehicleNo") if msg else None,
        "transporter_id":     msg.get("transporterId") if msg else None,
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

def save_consolidated(
    *,
    company_id: str,
    branch_id: str,
    cewb_number: str,
    cewb_date: str | None,
    vehicle_number: str | None,
    user_gstin: str | None,
    from_state: str | None,
    ewb_numbers: list[str],
    raw_response: dict,
    created_by: str,
    pdf_url: str | None = None,
) -> dict:
    """Insert a row into ewb_consolidated."""
    db = get_client()
    row = {
        "company_id":     company_id,
        "branch_id":      branch_id,
        "cewb_number":    cewb_number,
        "cewb_date":      cewb_date,
        "vehicle_number": vehicle_number,
        "user_gstin":     user_gstin,
        "from_state":     from_state,
        "ewb_numbers":    ewb_numbers,
        "pdf_url":        pdf_url,
        "raw_response":   raw_response,
        "created_by":     created_by,
    }
    res = db.table("ewb_consolidated").insert(row).execute()
    return res.data[0] if res.data else row


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
