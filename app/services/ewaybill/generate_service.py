"""
Generate individual and consolidated E-Way Bills, with DB persistence.
"""
import logging

from app.services.ewaybill.nic_client import nic_post
from app.services.ewaybill.validators import (
    validate_generate_payload,
    normalise_generate_payload,
    validate_consolidate_payload,
)
from app.services.ewaybill.db import (
    upsert_ewb_record,
    insert_validation_log,
    insert_event,
    save_consolidated,
    link_ewbs_to_cewb,
)
from app.services.utils.supabase import get_client

logger = logging.getLogger("movesure.ewaybill.generate")


def generate_ewaybill(
    raw_payload: dict,
    *,
    company_id: str | None = None,
    branch_id: str | None = None,
    user_id: str | None = None,
    bilty_id: str | None = None,
) -> dict:
    """
    Generate a new EWB on NIC and persist to DB.
    DB writes: insert ewb_records, ewb_validation_log (v1), ewb_events (GENERATED).
    """
    payload = normalise_generate_payload(raw_payload)
    validate_generate_payload(payload)

    data = nic_post("ewayBillsGenerate/", payload)
    results = data.get("results", {})
    msg = results.get("message", {})

    ewb_number = msg.get("ewbNo") or msg.get("eway_bill_number")
    ewb_date   = msg.get("ewbDt")  or msg.get("eway_bill_date")
    valid_upto = msg.get("ewbValidTill") or msg.get("valid_upto")

    ewb_record = None
    if company_id and branch_id and user_id and ewb_number:
        ewb_record = upsert_ewb_record(
            company_id=company_id,
            branch_id=branch_id,
            eway_bill_number=str(ewb_number),
            ewb_status="ACTIVE",
            raw_response=data,
            created_by=user_id,
            bilty_id=bilty_id,
            doc_number=payload.get("document_number"),
            doc_date=payload.get("document_date"),
            doc_type=payload.get("document_type"),
            gstin_of_generator=payload.get("userGstin"),
            gstin_of_consignor=payload.get("gstin_of_consignor"),
            gstin_of_consignee=payload.get("gstin_of_consignee"),
            transporter_id=payload.get("transporter_id"),
            transporter_name=payload.get("transporter_name"),
            vehicle_number=payload.get("vehicle_number"),
            from_state=payload.get("state_of_consignor"),
            to_state=payload.get("state_of_supply"),
            from_pincode=payload.get("pincode_of_consignor"),
            to_pincode=payload.get("pincode_of_consignee"),
            ewb_date=ewb_date,
            valid_upto=valid_upto,
            items_json=payload.get("itemList"),
            supply_type=payload.get("supply_type"),
            transport_mode=payload.get("transportation_mode"),
            transport_distance=payload.get("transportation_distance"),
            total_value=payload.get("total_invoice_value"),
        )
        ewb_id = ewb_record.get("id")

        if ewb_id:
            insert_validation_log(
                ewb_id=ewb_id,
                eway_bill_number=str(ewb_number),
                nic_response=data,
                company_id=company_id,
                branch_id=branch_id,
                created_by=user_id,
                triggered_by="GENERATE",
            )
            insert_event(
                ewb_id=ewb_id,
                eway_bill_number=str(ewb_number),
                event_type="GENERATED",
                company_id=company_id,
                branch_id=branch_id,
                created_by=user_id,
                raw_response=data,
                notes="EWB generated via NIC",
            )

    return {
        "status":           "success",
        "message":          "E-Way Bill generated successfully",
        "eway_bill_number": ewb_number,
        "eway_bill_date":   ewb_date,
        "valid_upto":       valid_upto,
        "data":             msg,
        **({"ewb_record_id": ewb_record.get("id")} if ewb_record else {}),
    }


def generate_consolidated_ewaybill(
    raw_payload: dict,
    *,
    company_id: str | None = None,
    branch_id: str | None = None,
    user_id: str | None = None,
    trip_sheet_id: str | None = None,
) -> dict:
    """
    Generate a Consolidated EWB and persist to DB.
    DB writes: insert ewb_consolidated, ewb_events (CONSOLIDATED),
               update member ewb_records.cewb_id.
    """
    payload = dict(raw_payload)
    validate_consolidate_payload(payload)

    # Accept flat string list → object list
    ewb_list = payload["list_of_eway_bills"]
    if ewb_list and isinstance(ewb_list[0], str):
        payload["list_of_eway_bills"] = [{"eway_bill_number": n} for n in ewb_list]
    ewb_numbers = [
        str(item) if isinstance(item, str) else str(item.get("eway_bill_number", ""))
        for item in (raw_payload.get("list_of_eway_bills") or [])
    ]

    data = nic_post("consolidatedEwayBillsGenerate/", payload)
    results = data.get("results", {})
    msg = results.get("message", {})

    cewb_no   = msg.get("cEwbNo")
    cewb_date = msg.get("cEwbDate")
    raw_url   = msg.get("url") or msg.get("pdf_url")
    pdf_url   = ("https://" + raw_url) if raw_url and not raw_url.startswith("http") else raw_url

    cewb_record = None
    if company_id and branch_id and user_id and cewb_no:
        cewb_record = save_consolidated(
            company_id=company_id,
            branch_id=branch_id,
            cewb_number=str(cewb_no),
            cewb_date=cewb_date,
            vehicle_number=payload.get("vehicle_number"),
            place_of_consignor=payload.get("place_of_consignor"),
            state_of_consignor=payload.get("state_of_consignor"),
            mode_of_transport=payload.get("mode_of_transport"),
            transporter_doc_number=payload.get("transporter_document_number"),
            transporter_doc_date=payload.get("transporter_document_date"),
            ewb_numbers=ewb_numbers,
            raw_response=data,
            created_by=user_id,
            pdf_url=pdf_url,
            trip_sheet_id=trip_sheet_id,
        )
        cewb_id = cewb_record.get("cewb_id")
        if cewb_id:
            link_ewbs_to_cewb(cewb_id, ewb_numbers, company_id)
            # Log a CONSOLIDATED event on each member ewb_record (ewb_events.ewb_id → ewb_records FK)
            db = get_client()
            member_records = (
                db.table("ewb_records")
                .select("ewb_id, eway_bill_number")
                .eq("company_id", company_id)
                .in_("eway_bill_number", ewb_numbers)
                .execute()
            )
            for member in (member_records.data or []):
                insert_event(
                    ewb_id=member["ewb_id"],
                    eway_bill_number=member["eway_bill_number"],
                    event_type="CONSOLIDATED",
                    company_id=company_id,
                    branch_id=branch_id,
                    created_by=user_id,
                    raw_response=data,
                    reference_id=cewb_id,
                    event_data={"cewb_number": str(cewb_no), "cewb_id": cewb_id},
                    notes=f"Included in Consolidated EWB {cewb_no}",
                )

    return {
        "status":  "success",
        "message": "Consolidated E-Way Bill created successfully",
        "cEwbNo":  cewb_no,
        "cEwbDate": cewb_date,
        "url":     pdf_url,
        "data":    msg,
        **({"cewb_record_id": cewb_record.get("cewb_id")} if cewb_record else {}),
    }
