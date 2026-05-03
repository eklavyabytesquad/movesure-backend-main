"""
Fetch / validate an existing E-Way Bill from NIC and persist to DB.
"""
import logging

from app.services.ewaybill.nic_client import nic_get
from app.services.ewaybill.db import (
    upsert_ewb_record,
    insert_validation_log,
    insert_event,
    get_validation_history,
    get_ewb_record,
)

logger = logging.getLogger("movesure.ewaybill.records")


def _extract_record_fields(msg: dict) -> dict:
    """Pull key fields from NIC GetEwayBill message."""
    return {
        "doc_number":          msg.get("docNo"),
        "doc_date":            msg.get("docDate"),
        "doc_type":            msg.get("docType"),
        "gstin_of_generator":  msg.get("genGstin"),
        "gstin_of_consignor":  msg.get("fromGstin"),
        "gstin_of_consignee":  msg.get("toGstin"),
        "transporter_id":      msg.get("transporterId"),
        "transporter_name":    msg.get("transporterName"),
        "vehicle_number":      msg.get("vehicleNo"),
        "from_state":          str(msg.get("fromStateCode", "")) or None,
        "to_state":            str(msg.get("toStateCode", "")) or None,
        "ewb_date":            msg.get("ewbDt"),
        "valid_upto":          msg.get("ewbValidTill"),
        "supply_type":         msg.get("supplyType"),
        "transport_mode":      str(msg.get("transportMode", "")) or None,
        "transport_distance":  msg.get("actDistance"),
        "total_value":         msg.get("totalValue"),
    }


def fetch_ewaybill(
    eway_bill_number: str,
    gstin: str,
    *,
    company_id: str | None = None,
    branch_id: str | None = None,
    user_id: str | None = None,
    bilty_id: str | None = None,
    force_refresh: bool = False,
) -> dict:
    """
    Fetch EWB from NIC and (if company_id provided) save to DB.
    DB writes: upsert ewb_records, insert ewb_validation_log, insert ewb_events.

    force_refresh=False (default): if the EWB already exists in ewb_records,
      return the cached DB record WITHOUT calling NIC. This prevents the
      validate-tab from triggering a live NIC call on every page visit.
    force_refresh=True: always call NIC, save a new validation_log version.
    """
    # ── Short-circuit: return DB record if not forcing refresh ──
    if not force_refresh and company_id:
        existing = get_ewb_record(company_id, str(eway_bill_number))
        if existing:
            history = get_validation_history(company_id, str(eway_bill_number))
            latest = history[0] if history else None
            return {
                "status":  "success",
                "message": "E-Way Bill details retrieved from cache (no NIC call made)",
                "data":    existing.get("raw_response") or {},
                "source":  "cache",
                "is_previously_validated": len(history) > 0,
                "total_validations":       len(history),
                "latest_version_no":       latest["version_no"] if latest else None,
                "latest_nic_status":       latest["nic_status"] if latest else None,
                "latest_validated_at":     latest["validated_at"] if latest else None,
                "ewb_record_id":           existing.get("ewb_id"),
            }
    # ── Live NIC call ──────────────────────────────────────────
    data = nic_get(
        "getEwayBillData/",
        {"action": "GetEwayBill", "gstin": gstin, "eway_bill_number": eway_bill_number},
    )

    # ── DB writes (only when caller supplies auth context) ──
    ewb_record = None
    if company_id and branch_id and user_id:
        results = data.get("results", {})
        msg = results.get("message", {}) if isinstance(results.get("message"), dict) else {}
        fields = _extract_record_fields(msg)

        ewb_record = upsert_ewb_record(
            company_id=company_id,
            branch_id=branch_id,
            eway_bill_number=str(eway_bill_number),
            ewb_status="ACTIVE",
            raw_response=data,
            created_by=user_id,
            bilty_id=bilty_id,
            **{k: v for k, v in fields.items() if v is not None},
        )
        # Supabase returns rows with the actual column name — PK is `ewb_id`, not `id`
        ewb_id = ewb_record.get("ewb_id")

        if ewb_id:
            insert_validation_log(
                ewb_id=ewb_id,
                eway_bill_number=str(eway_bill_number),
                nic_response=data,
                company_id=company_id,
                branch_id=branch_id,
                created_by=user_id,
                triggered_by="manual",   # user-triggered validate call
            )
            insert_event(
                ewb_id=ewb_id,
                eway_bill_number=str(eway_bill_number),
                event_type="VALIDATED",
                company_id=company_id,
                branch_id=branch_id,
                created_by=user_id,
                raw_response=data,
                event_data={"version_no": 1, "nic_status": "ACTIVE"},
                notes="EWB fetched and validated from NIC",
            )

        else:
            logger.warning(
                "fetch_ewaybill: ewb_id missing from upsert result for EWB %s — "
                "validation log not saved. Check if ewb_records PK is 'ewb_id'.",
                eway_bill_number,
            )

    # Build enriched response — always include validation history if we have context
    validation_summary: dict = {}
    if company_id:
        history = get_validation_history(company_id, str(eway_bill_number))
        latest = history[0] if history else None
        validation_summary = {
            "is_previously_validated": len(history) > 0,
            "total_validations":       len(history),
            "latest_version_no":       latest["version_no"] if latest else None,
            "latest_nic_status":       latest["nic_status"] if latest else None,
            "latest_validated_at":     latest["validated_at"] if latest else None,
        }

    return {
        "status":  "success",
        "message": "E-Way Bill details retrieved successfully",
        "source":  "nic",
        "data":    data,
        **validation_summary,
        **({"ewb_record_id": ewb_record.get("ewb_id")} if ewb_record else {}),
    }
