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


def _normalise_date(val: str | None) -> str | None:
    """Convert DD/MM/YYYY or DD/MM/YYYY HH:MM:SS to ISO YYYY-MM-DD, pass through ISO dates unchanged."""
    if not val:
        return None
    val = str(val).strip()
    # Already ISO
    if len(val) >= 10 and val[4] == "-":
        return val[:10]
    # DD/MM/YYYY [HH:MM:SS [AP]M]
    try:
        from datetime import datetime
        for fmt in ("%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
            try:
                return datetime.strptime(val.split(" AM")[0].split(" PM")[0].strip(), fmt.split(" ")[0]).strftime("%Y-%m-%d")
            except ValueError:
                pass
        # Try with full format
        parts = val.split()
        if len(parts) >= 1:
            d, m, y = parts[0].split("/")
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    except Exception:
        pass
    return None  # don't save unparseable dates


def _normalise_vehicle_type(val: str | None) -> str | None:
    """Map NIC vehicle_type to DB allowed values: 'Regular', 'ODC', or NULL."""
    if not val:
        return None
    v = str(val).strip().lower()
    if v == "odc":
        return "ODC"
    if v:
        return "Regular"
    return None


def _extract_record_fields(msg: dict) -> dict:
    """Pull key fields from NIC GetEwayBill message.
    Handles both camelCase (old NIC format) and snake_case (new NIC/Masters India format).
    Returns keys that match actual ewb_records DB column names.
    """
    def _get(*keys):
        for k in keys:
            v = msg.get(k)
            if v is not None and v != "":
                return v
        return None

    return {
        "document_number":       _get("docNo", "document_number"),
        "document_date":         _normalise_date(_get("docDate", "document_date")),
        "document_type":         _get("docType", "document_type"),
        "generated_by_gstin":    _get("genGstin", "userGstin"),
        "gstin_of_consignor":    _get("fromGstin", "gstin_of_consignor"),
        "consignor_name":        _get("legal_name_of_consignor"),
        "pincode_of_consignor":  _get("pincode_of_consignor"),
        "state_of_consignor":    _get("state_of_consignor", "actual_from_state_name"),
        "gstin_of_consignee":    _get("toGstin", "gstin_of_consignee"),
        "consignee_name":        _get("legal_name_of_consignee"),
        "pincode_of_consignee":  _get("pincode_of_consignee"),
        "state_of_supply":       _get("state_of_supply", "actual_to_state_name"),
        "transporter_id":        _get("transporterId", "transporter_id"),
        "transporter_name":      _get("transporterName", "transporter_name"),
        "vehicle_number":        _get("vehicleNo", "vehicle_number"),
        "vehicle_type":          _normalise_vehicle_type(_get("vehicleType", "vehicle_type")),
        "eway_bill_date":        _normalise_date(_get("ewbDt", "eway_bill_date")),
        "valid_upto":            _normalise_date(_get("ewbValidTill", "eway_bill_valid_date")),
        "supply_type":           _get("supplyType", "supply_type"),
        "sub_supply_type":       _get("subSupplyType", "sub_supply_type"),
        "transportation_mode":   _get("transportMode", "transportation_mode"),
        "transportation_distance": _get("actDistance", "transportation_distance"),
        "total_invoice_value":   _get("totalValue", "total_invoice_value"),
        "taxable_amount":        _get("taxableAmount", "taxable_amount"),
        "vehicle_type":          _normalise_vehicle_type(_get("vehicleType", "vehicle_type")),
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
    # Skip cache if raw_response is empty {} — means the record was manually
    # seeded without a real NIC call, so we must fetch from NIC.
    if not force_refresh and company_id:
        existing = get_ewb_record(company_id, str(eway_bill_number))
        if existing and existing.get("raw_response"):
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
