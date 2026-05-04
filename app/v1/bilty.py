import logging
from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

logger = logging.getLogger("movesure.bilty")

from app.middleware.auth import get_current_user
from app.services.bilty.service import (
    next_gr_no,
    create_bilty,
    list_bilties,
    get_bilty,
    update_bilty,
    delete_bilty,
)
from app.services.bilty_setting.service import (
    get_primary_book,
    get_primary_template,
    peek_gr_no,
)
from app.services.challan.service import (
    get_primary_challan,
    add_bilty_to_challan,
)

router = APIRouter(prefix="/bilty", tags=["Bilty"])


# ══════════════════════════════════════════════════════════════
# Pydantic models
# ══════════════════════════════════════════════════════════════

class BiltyCreate(BaseModel):
    # GR / Book
    # gr_no is optional — if omitted the backend auto-claims from the primary book
    gr_no:               str | None     = Field(None, max_length=50)
    book_id:             str | None     = None
    bilty_type:          str            = Field("REGULAR", pattern="^(REGULAR|MANUAL)$")
    bilty_date:          str | None     = None          # ISO date; defaults to today in DB

    # Consignor snapshot
    consignor_id:        str | None     = None
    consignor_name:      str            = Field(..., min_length=1, max_length=255)
    consignor_gstin:     str | None     = Field(None, max_length=15)
    consignor_mobile:    str | None     = Field(None, max_length=15)

    # Consignee snapshot
    consignee_id:        str | None     = None
    consignee_name:      str | None     = Field(None, max_length=255)
    consignee_gstin:     str | None     = Field(None, max_length=15)
    consignee_mobile:    str | None     = Field(None, max_length=15)

    # Transport snapshot
    transport_id:        str | None     = None
    transport_name:      str | None     = Field(None, max_length=255)
    transport_gstin:     str | None     = Field(None, max_length=15)
    transport_mobile:    str | None     = Field(None, max_length=15)

    # Route
    from_city_id:        str | None     = None
    to_city_id:          str | None     = None

    # Shipment
    delivery_type:       str | None     = Field(None, pattern="^(DOOR|GODOWN)$")
    payment_mode:        str | None     = Field(None, pattern="^(PAID|TO-PAY|FOC)$")
    contain:             str | None     = None
    invoice_no:          str | None     = Field(None, max_length=100)
    invoice_value:       float          = 0.0
    invoice_date:        str | None     = None
    # Array of e-way bill objects: [{"ewb_no": "...", "valid_upto": "...", "vehicle_no": "..."}]
    e_way_bills:         list[dict[str, Any]] = []
    document_number:     str | None     = Field(None, max_length=100)
    no_of_pkg:           int            = Field(0, ge=0)
    weight:              float | None   = None           # billed weight
    actual_weight:       float | None   = None           # physical/actual weight
    rate:                float | None   = None
    pvt_marks:           str | None     = None

    # Charges
    freight_amount:      float          = 0.0
    labour_rate:         float | None   = None
    labour_charge:       float          = 0.0
    bill_charge:         float          = 0.0
    toll_charge:         float          = 0.0
    dd_charge:           float          = 0.0
    pf_charge:           float          = 0.0
    other_charge:        float          = 0.0
    local_charge:        float          = 0.0
    discount_id:         str | None     = None
    discount_percentage: float          = Field(0.0, ge=0, le=100)
    discount_amount:     float          = Field(0.0, ge=0)
    total_amount:        float          = 0.0

    # Template (overrides book-level template for this bilty)
    template_id:         str | None     = None

    # Save / status
    saving_option:       str            = Field("SAVE", pattern="^(SAVE|DRAFT|PRINT)$")
    status:              str            = Field("SAVED", pattern="^(DRAFT|SAVED)$")

    remark:              str | None     = None
    metadata:            dict[str, Any] = {}
    tracking_meta:       dict[str, Any] = {}


class BiltyUpdate(BaseModel):
    # Consignee snapshot (may be filled after booking)
    consignee_id:          str | None     = None
    consignee_name:        str | None     = Field(None, max_length=255)
    consignee_gstin:       str | None     = Field(None, max_length=15)
    consignee_mobile:      str | None     = Field(None, max_length=15)

    # Transport snapshot
    transport_id:          str | None     = None
    transport_name:        str | None     = Field(None, max_length=255)
    transport_gstin:       str | None     = Field(None, max_length=15)
    transport_mobile:      str | None     = Field(None, max_length=15)

    # Route
    from_city_id:          str | None     = None
    to_city_id:            str | None     = None

    # Shipment fields
    delivery_type:         str | None     = Field(None, pattern="^(DOOR|GODOWN)$")
    payment_mode:          str | None     = Field(None, pattern="^(PAID|TO-PAY|FOC)$")
    contain:               str | None     = None
    invoice_no:            str | None     = Field(None, max_length=100)
    invoice_value:         float | None   = None
    invoice_date:          str | None     = None
    e_way_bills:           list[dict[str, Any]] | None = None
    document_number:       str | None     = Field(None, max_length=100)
    no_of_pkg:             int | None     = Field(None, ge=0)
    weight:                float | None   = None
    actual_weight:         float | None   = None
    rate:                  float | None   = None
    pvt_marks:             str | None     = None

    # Charges
    freight_amount:        float | None   = None
    labour_rate:           float | None   = None
    labour_charge:         float | None   = None
    bill_charge:           float | None   = None
    toll_charge:           float | None   = None
    dd_charge:             float | None   = None
    pf_charge:             float | None   = None
    other_charge:          float | None   = None
    local_charge:          float | None   = None
    discount_id:           str | None     = None
    discount_percentage:   float | None   = Field(None, ge=0, le=100)
    discount_amount:       float | None   = Field(None, ge=0)
    total_amount:          float | None   = None

    # Template override
    template_id:           str | None     = None

    # Status
    status:                str | None     = Field(None, pattern="^(DRAFT|SAVED|DISPATCHED|REACHED_HUB|AT_GODOWN|OUT_FOR_DELIVERY|DELIVERED|UNDELIVERED|CANCELLED|LOST)$")
    saving_option:         str | None     = Field(None, pattern="^(SAVE|DRAFT|PRINT)$")
    pdf_url:               str | None     = None

    # Lifecycle booleans + timestamps (set together)
    is_dispatched:         bool | None    = None
    dispatched_at:         str | None     = None
    dispatched_challan_no: str | None     = Field(None, max_length=50)

    is_reached_hub:        bool | None    = None
    reached_hub_at:        str | None     = None

    is_at_godown:          bool | None    = None
    at_godown_at:          str | None     = None

    is_out_for_delivery:   bool | None    = None
    out_for_delivery_at:   str | None     = None

    is_delivered:          bool | None    = None
    delivered_at:          str | None     = None
    delivery_remark:       str | None     = None
    pod_image_url:         str | None     = None

    remark:                str | None     = None
    tracking_meta:         dict[str, Any] | None = None
    metadata:              dict[str, Any] | None = None


class BiltyDeleteRequest(BaseModel):
    deletion_reason: str = Field(..., min_length=3, description="Reason for cancellation / deletion")


# ══════════════════════════════════════════════════════════════
# ROUTES
# NOTE: /next-gr          must come before /next-gr/{book_id}
#       /next-gr/{book_id} must come before /{bilty_id}
# ══════════════════════════════════════════════════════════════

@router.get(
    "/peek-gr/{book_id}",
    summary="Preview next GR number for a book (read-only, does NOT consume the number)",
    description=(
        "Returns the next available GR number for the given book WITHOUT incrementing "
        "current_number. Safe to call on every book-select in the UI. "
        "Use /next-gr/{book_id} only when the bilty is actually being created."
    ),
)
def api_peek_gr_no(
    book_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    return peek_gr_no(str(book_id), current_user["company_id"])


@router.get(
    "/next-gr",
    summary="Claim next GR from the branch primary book (no book selection needed)",
    description="Uses the primary REGULAR book for the caller's branch. Returns 404 if no primary book is set.",
)
def api_next_gr_primary(
    current_user: dict = Depends(get_current_user),
):
    book = get_primary_book(current_user["company_id"], current_user["branch_id"], "REGULAR")
    if not book:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No primary REGULAR book set for this branch. Go to Settings → Books and mark one as primary.",
        )
    result = next_gr_no(book["book_id"])
    return {"gr_no": result["gr_no"], "gr_number": result["gr_number"], "book_id": book["book_id"]}

@router.get(
    "/next-gr/{book_id}",
    summary="Atomically claim the next GR number from a bilty book",
    description=(
        "Calls fn_next_gr_no(book_id) inside a DB transaction. "
        "Returns the formatted GR string and the raw integer. "
        "Returns 410 if the book is exhausted, 404 if inactive/not found."
    ),
)
def api_next_gr_no(
    book_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    result = next_gr_no(str(book_id))
    return {"gr_no": result["gr_no"], "gr_number": result["gr_number"], "book_id": str(book_id)}


@router.post(
    "",
    status_code=201,
    summary="Create a new bilty (REGULAR or MANUAL)",
    description=(
        "For REGULAR bilties: if gr_no and book_id are omitted the backend auto-claims "
        "the next GR from the branch primary book and auto-applies the primary template. "
        "You can still pass book_id explicitly to use a specific book. "
        "For MANUAL bilties provide gr_no directly and set bilty_type=MANUAL."
    ),
)
def api_create_bilty(
    body: BiltyCreate,
    current_user: dict = Depends(get_current_user),
):
    company_id = current_user["company_id"]
    branch_id  = current_user["branch_id"]

    data = body.model_dump()
    data["company_id"] = company_id
    data["branch_id"]  = branch_id
    data["created_by"] = current_user["sub"]
    data["updated_by"] = current_user["sub"]

    if body.bilty_type == "REGULAR":
        # Auto-resolve book from primary if not explicitly provided
        if not data.get("book_id"):
            book = get_primary_book(company_id, branch_id, "REGULAR")
            if not book:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "No primary REGULAR book set for this branch. Go to Settings → Books and mark one as primary.",
                )
            data["book_id"] = book["book_id"]

        # Auto-claim GR if not explicitly provided
        if not data.get("gr_no"):
            gr = next_gr_no(data["book_id"])
            data["gr_no"] = gr["gr_no"]

    elif body.bilty_type == "MANUAL":
        if not data.get("gr_no"):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "gr_no is required for MANUAL bilties.",
            )
        # Apply defaults from the primary MANUAL book (if one exists).
        # book_defaults can carry: from_city_id, to_city_id,
        # delivery_type, payment_mode, transport_id.
        # Only fills a field when the request body did NOT already provide it.
        manual_book = get_primary_book(company_id, branch_id, "MANUAL")
        if manual_book:
            data["book_id"] = manual_book["book_id"]
            for key in ("delivery_type", "payment_mode",
                        "from_city_id", "to_city_id", "transport_id"):
                if not data.get(key) and manual_book.get("book_defaults", {}).get(key):
                    data[key] = manual_book["book_defaults"][key]

    # Auto-apply primary template if none specified
    if not data.get("template_id"):
        tmpl = get_primary_template(company_id, branch_id)
        if tmpl:
            data["template_id"] = tmpl["template_id"]

    result = create_bilty(data)

    # Auto-assign to primary challan (only for SAVED bilties, silently skipped if none exists)
    if data.get("status", "SAVED") == "SAVED":
        primary_challan = get_primary_challan(company_id, branch_id)
        if primary_challan:
            try:
                add_bilty_to_challan(
                    primary_challan["challan_id"],
                    result["bilty_id"],
                    company_id,
                    current_user["sub"],
                )
                result["challan_id"] = primary_challan["challan_id"]
                result["challan_no"] = primary_challan["challan_no"]
            except Exception:
                # Non-fatal — bilty is created; challan assignment failed gracefully
                logger.warning(
                    "auto_assign_challan failed | bilty=%s challan=%s",
                    result.get("bilty_id"), primary_challan["challan_id"],
                )

    return {"message": "Bilty created.", "bilty": result}


@router.get(
    "",
    summary="List bilties for the caller's branch",
)
def api_list_bilties(
    bilty_type:   str | None = Query(None, pattern="^(REGULAR|MANUAL)$"),
    status:       str | None = Query(None, alias="status"),
    payment_mode: str | None = Query(None, pattern="^(PAID|TO-PAY|FOC)$"),
    consignor_id: str | None = Query(None),
    consignee_id: str | None = Query(None),
    from_date:    str | None = Query(None, description="ISO date e.g. 2026-01-01"),
    to_date:      str | None = Query(None, description="ISO date e.g. 2026-04-30"),
    is_active:    bool       = Query(True),
    limit:        int        = Query(50, ge=1, le=500),
    offset:       int        = Query(0, ge=0),
    current_user: dict       = Depends(get_current_user),
):
    rows = list_bilties(
        company_id=current_user["company_id"],
        branch_id=current_user["branch_id"],
        bilty_type=bilty_type,
        status_filter=status,
        payment_mode=payment_mode,
        consignor_id=consignor_id,
        consignee_id=consignee_id,
        from_date=from_date,
        to_date=to_date,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    return {"count": len(rows), "bilties": rows}


@router.get(
    "/{bilty_id}",
    summary="Get a single bilty by ID",
)
def api_get_bilty(
    bilty_id: str,
    current_user: dict = Depends(get_current_user),
):
    row = get_bilty(bilty_id, current_user["company_id"])
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bilty not found")
    return row


@router.patch(
    "/{bilty_id}",
    summary="Update bilty fields or advance lifecycle status",
)
def api_update_bilty(
    bilty_id: str,
    body: BiltyUpdate,
    current_user: dict = Depends(get_current_user),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    data["updated_by"] = current_user["sub"]

    # Attach lifecycle _by fields automatically when booleans are flipped on
    user_id = current_user["sub"]
    if data.get("is_dispatched"):
        data.setdefault("dispatched_by", user_id)
    if data.get("is_reached_hub"):
        data.setdefault("reached_hub_by", user_id)
    if data.get("is_at_godown"):
        data.setdefault("at_godown_by", user_id)
    if data.get("is_out_for_delivery"):
        data.setdefault("out_for_delivery_by", user_id)
    if data.get("is_delivered"):
        data.setdefault("delivered_by", user_id)

    result = update_bilty(bilty_id, current_user["company_id"], data)
    return {"message": "Bilty updated.", "bilty": result}


@router.delete(
    "/{bilty_id}",
    summary="Soft-delete (cancel) a bilty — sets is_active=False and status=CANCELLED",
)
def api_delete_bilty(
    bilty_id: str,
    body: BiltyDeleteRequest,
    current_user: dict = Depends(get_current_user),
):
    result = delete_bilty(
        bilty_id=bilty_id,
        company_id=current_user["company_id"],
        deleted_by=current_user["sub"],
        deletion_reason=body.deletion_reason,
    )
    return {"message": "Bilty cancelled.", "bilty": result}
