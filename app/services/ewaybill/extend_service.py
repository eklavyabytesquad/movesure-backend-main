"""
Extend E-Way Bill validity with DB persistence.
"""
import logging

from app.services.ewaybill.nic_client import nic_post
from app.services.ewaybill.validators import validate_extend_payload
from app.services.ewaybill.db import (
    update_ewb_record_fields,
    insert_validation_log,
    insert_event,
    get_ewb_record,
)

logger = logging.getLogger("movesure.ewaybill.extend")


def extend_ewaybill(
    raw_payload: dict,
    *,
    company_id: str | None = None,
    branch_id: str | None = None,
    user_id: str | None = None,
) -> dict:
    """
    Extend EWB validity window.
    DB writes: update ewb_records (valid_upto, status=EXTENDED),
               insert ewb_validation_log, insert ewb_events (EXTENDED).
    """
    payload = validate_extend_payload(dict(raw_payload))

    data = nic_post("ewayBillValidityExtend/", payload)
    results = data.get("results", {})
    msg = results.get("message", {})

    ewb_number  = str(payload["eway_bill_number"])
    new_valid   = msg.get("validUpto") or msg.get("new_valid_upto")

    if company_id and branch_id and user_id:
        # patch status + new valid_upto
        update_ewb_record_fields(
            company_id=company_id,
            eway_bill_number=ewb_number,
            updates={
                "ewb_status":   "EXTENDED",
                "valid_upto":   new_valid,
                "raw_response": data,
            },
        )
        existing = get_ewb_record(company_id, ewb_number)
        ewb_id = existing.get("id") if existing else None

        if ewb_id:
            insert_validation_log(
                ewb_id=ewb_id,
                eway_bill_number=ewb_number,
                nic_response=data,
                company_id=company_id,
                branch_id=branch_id,
                created_by=user_id,
                triggered_by="EXTEND",
            )
            insert_event(
                ewb_id=ewb_id,
                eway_bill_number=ewb_number,
                event_type="EXTENDED",
                company_id=company_id,
                branch_id=branch_id,
                created_by=user_id,
                raw_response=data,
                event_data={"new_valid_upto": new_valid},
                notes=f"Validity extended to {new_valid}",
            )

    return {
        "status":           "success",
        "message":          "E-Way Bill validity extended successfully",
        "eway_bill_number": ewb_number,
        "new_valid_upto":   new_valid,
        "data":             msg,
    }
