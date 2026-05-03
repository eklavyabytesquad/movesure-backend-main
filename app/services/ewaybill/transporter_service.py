"""
Transporter assignment / update with DB persistence.
"""
import logging

from app.services.ewaybill.nic_client import nic_post
from app.services.ewaybill.db import update_ewb_record_fields, insert_event, get_ewb_record

logger = logging.getLogger("movesure.ewaybill.transporter")


def _validate_transporter_payload(payload: dict) -> dict:
    required = ["userGstin", "eway_bill_number", "transporter_id"]
    missing = [f for f in required if payload.get(f) in (None, "")]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")
    payload = dict(payload)
    payload["eway_bill_number"] = int(payload["eway_bill_number"])
    return payload


def update_transporter(
    raw_payload: dict,
    *,
    company_id: str | None = None,
    branch_id: str | None = None,
    user_id: str | None = None,
) -> dict:
    """
    Assign / change transporter on an EWB.
    DB writes: update ewb_records (transporter fields), insert ewb_events.
    """
    payload = _validate_transporter_payload(raw_payload)

    data = nic_post("transporterIdUpdate/", payload)
    results = data.get("results", {})
    msg = results.get("message", {})

    ewb_number = str(payload["eway_bill_number"])
    transporter_id = payload.get("transporter_id")

    if company_id and branch_id and user_id:
        # patch transporter fields on the existing record
        update_ewb_record_fields(
            company_id=company_id,
            eway_bill_number=ewb_number,
            updates={
                "transporter_id":   transporter_id,
                "transporter_name": payload.get("transporter_name"),
                "raw_response":     data,
            },
        )
        # log event — fetch record id for FK
        existing = get_ewb_record(company_id, ewb_number)
        ewb_id = existing.get("id") if existing else None
        if ewb_id:
            insert_event(
                ewb_id=ewb_id,
                eway_bill_number=ewb_number,
                event_type="TRANSPORTER_UPDATED",
                company_id=company_id,
                branch_id=branch_id,
                created_by=user_id,
                raw_response=data,
                event_data={"transporter_id": transporter_id},
            )

    return {
        "status":           "success",
        "message":          "Transporter ID updated successfully",
        "eway_bill_number": ewb_number,
        "transporter_id":   transporter_id,
        "update_date":      msg.get("updDate") or msg.get("update_date"),
        "pdf_url":          msg.get("pdfUrl") or msg.get("pdf_url"),
        "data":             msg,
    }


def update_transporter_with_pdf(
    raw_payload: dict,
    *,
    company_id: str | None = None,
    branch_id: str | None = None,
    user_id: str | None = None,
) -> dict:
    """
    Update transporter then make a second call to fetch the updated PDF.
    DB writes: update ewb_records, insert ewb_events (TRANSPORTER_PDF).
    """
    payload = _validate_transporter_payload(raw_payload)
    ewb_number = str(payload["eway_bill_number"])
    transporter_id = payload.get("transporter_id")

    # Call 1 — apply update
    data1 = nic_post("transporterIdUpdate/", payload)
    msg1 = data1.get("results", {}).get("message", {})

    # Call 2 — fetch PDF
    data2 = nic_post("transporterIdUpdate/", payload)
    msg2 = data2.get("results", {}).get("message", {})

    has_pdf = "pdf" in str(data2).lower() or "base64" in str(data2).lower()

    if company_id and branch_id and user_id:
        update_ewb_record_fields(
            company_id=company_id,
            eway_bill_number=ewb_number,
            updates={
                "transporter_id":   transporter_id,
                "transporter_name": payload.get("transporter_name"),
                "raw_response":     data2,
            },
        )
        existing = get_ewb_record(company_id, ewb_number)
        ewb_id = existing.get("id") if existing else None
        if ewb_id:
            insert_event(
                ewb_id=ewb_id,
                eway_bill_number=ewb_number,
                event_type="TRANSPORTER_PDF",
                company_id=company_id,
                branch_id=branch_id,
                created_by=user_id,
                raw_response=data2,
                event_data={"transporter_id": transporter_id, "pdf_found": has_pdf},
            )

    return {
        "status":           "success",
        "message":          "Transporter updated and PDF fetched" if has_pdf else "Transporter updated (PDF not available)",
        "eway_bill_number": ewb_number,
        "transporter_id":   transporter_id,
        "update_result":    msg1,
        "pdf_result":       msg2,
        "pdf_found":        has_pdf,
    }
