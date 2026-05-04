from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator, model_validator

from app.middleware.auth import get_current_user
from app.services.bilty_setting.service import (
    # Consignor
    create_consignor, list_consignors, get_consignor, update_consignor, delete_consignor,
    # Consignee
    create_consignee, list_consignees, get_consignee, update_consignee, delete_consignee,
    # Book
    create_book, list_books, get_book, update_book, delete_book,
    get_primary_book, set_primary_book,
    # Rate
    create_rate, list_rates, get_rate, update_rate, delete_rate,
    # Template
    create_template, list_templates, get_template, update_template, delete_template,
    get_primary_template, set_primary_template,
    # Discount
    create_discount, list_discounts, get_discount, update_discount, delete_discount,
)

router = APIRouter(prefix="/bilty-setting", tags=["Bilty Settings"])


def _resolve_branch(user: dict, body_branch_id: str | None) -> str:
    """
    Super-admins may override branch_id via the request body.
    All other roles always use their own JWT branch.
    """
    if body_branch_id and user.get("post_in_office") == "super_admin":
        return body_branch_id
    return user["branch_id"]


# ══════════════════════════════════════════════════════════════
# Pydantic models — Consignor
# ══════════════════════════════════════════════════════════════

class ConsignorCreate(BaseModel):
    consignor_name:   str            = Field(..., min_length=2, max_length=255)
    gstin:            str | None     = Field(None, max_length=15)
    pan:              str | None     = Field(None, max_length=10)
    aadhar:           str | None     = Field(None, max_length=12)
    address:          str | None     = None
    city:             str | None     = Field(None, max_length=150)
    state:            str | None     = Field(None, max_length=100)
    pincode:          str | None     = Field(None, max_length=10)
    mobile:           str | None     = Field(None, max_length=15)
    alternate_mobile: str | None     = Field(None, max_length=15)
    email:            str | None     = Field(None, max_length=255)
    metadata:         dict[str, Any] = {}


class ConsignorUpdate(BaseModel):
    consignor_name:   str | None     = Field(None, min_length=2, max_length=255)
    gstin:            str | None     = Field(None, max_length=15)
    pan:              str | None     = Field(None, max_length=10)
    aadhar:           str | None     = Field(None, max_length=12)
    address:          str | None     = None
    city:             str | None     = Field(None, max_length=150)
    state:            str | None     = Field(None, max_length=100)
    pincode:          str | None     = Field(None, max_length=10)
    mobile:           str | None     = Field(None, max_length=15)
    alternate_mobile: str | None     = Field(None, max_length=15)
    email:            str | None     = Field(None, max_length=255)
    is_active:        bool | None    = None
    metadata:         dict[str, Any] | None = None


# ══════════════════════════════════════════════════════════════
# Pydantic models — Consignee
# ══════════════════════════════════════════════════════════════

class ConsigneeCreate(BaseModel):
    consignee_name:   str            = Field(..., min_length=2, max_length=255)
    gstin:            str | None     = Field(None, max_length=15)
    pan:              str | None     = Field(None, max_length=10)
    aadhar:           str | None     = Field(None, max_length=12)
    address:          str | None     = None
    city:             str | None     = Field(None, max_length=150)
    state:            str | None     = Field(None, max_length=100)
    pincode:          str | None     = Field(None, max_length=10)
    mobile:           str | None     = Field(None, max_length=15)
    alternate_mobile: str | None     = Field(None, max_length=15)
    email:            str | None     = Field(None, max_length=255)
    metadata:         dict[str, Any] = {}


class ConsigneeUpdate(BaseModel):
    consignee_name:   str | None     = Field(None, min_length=2, max_length=255)
    gstin:            str | None     = Field(None, max_length=15)
    pan:              str | None     = Field(None, max_length=10)
    aadhar:           str | None     = Field(None, max_length=12)
    address:          str | None     = None
    city:             str | None     = Field(None, max_length=150)
    state:            str | None     = Field(None, max_length=100)
    pincode:          str | None     = Field(None, max_length=10)
    mobile:           str | None     = Field(None, max_length=15)
    alternate_mobile: str | None     = Field(None, max_length=15)
    email:            str | None     = Field(None, max_length=255)
    is_active:        bool | None    = None
    metadata:         dict[str, Any] | None = None


# ══════════════════════════════════════════════════════════════
# Pydantic models — Bilty Book
# ══════════════════════════════════════════════════════════════

class BookCreate(BaseModel):
    book_name:     str | None = Field(None, max_length=100)
    template_name: str | None = Field(None, max_length=100)
    template_id:   str | None = None   # FK to bilty_template
    bilty_type:    str        = Field("REGULAR", pattern="^(REGULAR|MANUAL)$")
    party_scope:   str        = Field("COMMON", pattern="^(COMMON|CONSIGNOR|CONSIGNEE)$")
    consignor_id:  str | None = None
    consignee_id:  str | None = None
    prefix:        str | None = Field(None, max_length=20)
    # REGULAR books: from_number and to_number are required.
    # MANUAL books:  leave both out — there is no GR series.
    from_number:   int | None = Field(None, ge=1)
    to_number:     int | None = Field(None, ge=1)
    digits:        int        = Field(4, ge=1, le=10)
    postfix:       str | None = Field(None, max_length=20)
    is_fixed:      bool       = False
    auto_continue: bool       = False
    metadata:      dict[str, Any] = {}
    # Pre-fill defaults applied to the create-bilty form.
    # Supported keys: delivery_type, payment_mode, from_city_id, to_city_id, transport_id
    book_defaults: dict[str, Any] = {}
    # Super-admin only: override the branch this book is created under.
    # Regular users: this field is silently ignored.
    branch_id: str | None = Field(None, description="Super-admin: target branch UUID. Ignored for other roles.")

    @model_validator(mode="after")
    def validate_series_for_type(self) -> "BookCreate":
        if self.bilty_type == "REGULAR":
            if self.from_number is None or self.to_number is None:
                raise ValueError("from_number and to_number are required for REGULAR books")
            if self.to_number < self.from_number:
                raise ValueError("to_number must be >= from_number")
        elif self.bilty_type == "MANUAL":
            if self.from_number is not None or self.to_number is not None:
                raise ValueError(
                    "from_number and to_number must not be set for MANUAL books — "
                    "there is no GR series. The GR is entered freely on each bilty."
                )
        return self


class BookUpdate(BaseModel):
    book_name:     str | None  = Field(None, max_length=100)
    template_name: str | None  = Field(None, max_length=100)
    template_id:   str | None  = None   # FK to bilty_template
    is_fixed:      bool | None = None
    auto_continue: bool | None = None
    is_active:     bool | None = None
    is_completed:  bool | None = None
    metadata:      dict[str, Any] | None = None
    book_defaults: dict[str, Any] | None = None  # update pre-fill defaults
    # Super-admin only: move book to a different branch on update.
    branch_id:     str | None = Field(None, description="Super-admin: target branch UUID. Ignored for other roles.")


# ══════════════════════════════════════════════════════════════
# Pydantic models — Bilty Rate
# ══════════════════════════════════════════════════════════════

class RateCreate(BaseModel):
    consignor_id:           str | None = None
    consignee_id:           str | None = None
    party_type:             str        = Field(..., pattern="^(CONSIGNOR|CONSIGNEE)$")
    destination_city_id:    str        = Field(..., description="UUID of destination city")
    transport_id:           str | None = None
    rate:                   float      = Field(0.0, ge=0)
    rate_unit:              str        = Field("PER_KG", pattern="^(PER_KG|PER_NAG)$")
    minimum_weight_kg:      float      = 0.0
    freight_minimum_amount: float      = 0.0
    labour_rate:            float      = Field(0.0, ge=0)
    labour_unit:            str | None = Field(None, pattern="^(PER_KG|PER_NAG|PER_BILTY)$")
    dd_charge_per_kg:       float      = 0.0
    dd_charge_per_nag:      float      = 0.0
    bilty_charge:           float      = 0.0
    receiving_slip_charge:  float      = 0.0
    is_toll_tax_applicable: bool       = False
    toll_tax_amount:        float      = 0.0
    is_no_charge:           bool       = False
    effective_from:         str | None = None   # ISO date string; defaults to today in DB
    effective_to:           str | None = None
    metadata:               dict[str, Any] = {}

    @field_validator("consignor_id", "consignee_id")
    @classmethod
    def validate_party(cls, v, info):
        return v  # cross-field check below

    def validate_party_consistency(self):
        if self.party_type == "CONSIGNOR" and not self.consignor_id:
            raise ValueError("consignor_id required when party_type is CONSIGNOR")
        if self.party_type == "CONSIGNEE" and not self.consignee_id:
            raise ValueError("consignee_id required when party_type is CONSIGNEE")
        if self.party_type == "CONSIGNOR" and self.consignee_id:
            raise ValueError("consignee_id must be null when party_type is CONSIGNOR")
        if self.party_type == "CONSIGNEE" and self.consignor_id:
            raise ValueError("consignor_id must be null when party_type is CONSIGNEE")


class RateUpdate(BaseModel):
    rate:                   float | None = Field(None, ge=0)
    rate_unit:              str | None   = Field(None, pattern="^(PER_KG|PER_NAG)$")
    minimum_weight_kg:      float | None = None
    freight_minimum_amount: float | None = None
    labour_rate:            float | None = Field(None, ge=0)
    labour_unit:            str | None   = Field(None, pattern="^(PER_KG|PER_NAG|PER_BILTY)$")
    dd_charge_per_kg:       float | None = None
    dd_charge_per_nag:      float | None = None
    bilty_charge:           float | None = None
    receiving_slip_charge:  float | None = None
    is_toll_tax_applicable: bool | None  = None
    toll_tax_amount:        float | None = None
    is_no_charge:           bool | None  = None
    effective_from:         str | None   = None
    effective_to:           str | None   = None
    is_active:              bool | None  = None
    metadata:               dict[str, Any] | None = None


# ══════════════════════════════════════════════════════════════
# ROUTES — CONSIGNOR
# ══════════════════════════════════════════════════════════════

@router.post(
    "/consignors",
    status_code=201,
    summary="Create a consignor (shipper) master record",
)
def api_create_consignor(
    body: ConsignorCreate,
    current_user: dict = Depends(get_current_user),
):
    data = body.model_dump()
    data["company_id"] = current_user["company_id"]
    data["branch_id"]  = current_user["branch_id"]
    data["created_by"] = current_user["sub"]
    data["updated_by"] = current_user["sub"]
    result = create_consignor(data)
    return {"message": "Consignor created.", "consignor": result}


@router.get(
    "/consignors",
    summary="List consignors for the caller's branch",
)
def api_list_consignors(
    search:    str | None = Query(None, description="Filter by name (case-insensitive)"),
    is_active: bool       = Query(True),
    current_user: dict    = Depends(get_current_user),
):
    rows = list_consignors(
        company_id=current_user["company_id"],
        branch_id=current_user["branch_id"],
        search=search,
        is_active=is_active,
    )
    return {"count": len(rows), "consignors": rows}


@router.get(
    "/consignors/{consignor_id}",
    summary="Get a single consignor by ID",
)
def api_get_consignor(
    consignor_id: str,
    current_user: dict = Depends(get_current_user),
):
    row = get_consignor(consignor_id, current_user["company_id"])
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consignor not found")
    return row


@router.patch(
    "/consignors/{consignor_id}",
    summary="Update a consignor",
)
def api_update_consignor(
    consignor_id: str,
    body: ConsignorUpdate,
    current_user: dict = Depends(get_current_user),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    data["updated_by"] = current_user["sub"]
    result = update_consignor(consignor_id, current_user["company_id"], data)
    return {"message": "Consignor updated.", "consignor": result}


@router.delete(
    "/consignors/{consignor_id}",
    summary="Soft-delete a consignor (sets is_active=False)",
)
def api_delete_consignor(
    consignor_id: str,
    current_user: dict = Depends(get_current_user),
):
    result = delete_consignor(consignor_id, current_user["company_id"], current_user["sub"])
    return {"message": "Consignor deactivated.", "consignor": result}


# ══════════════════════════════════════════════════════════════
# ROUTES — CONSIGNEE
# ══════════════════════════════════════════════════════════════

@router.post(
    "/consignees",
    status_code=201,
    summary="Create a consignee (receiver) master record",
)
def api_create_consignee(
    body: ConsigneeCreate,
    current_user: dict = Depends(get_current_user),
):
    data = body.model_dump()
    data["company_id"] = current_user["company_id"]
    data["branch_id"]  = current_user["branch_id"]
    data["created_by"] = current_user["sub"]
    data["updated_by"] = current_user["sub"]
    result = create_consignee(data)
    return {"message": "Consignee created.", "consignee": result}


@router.get(
    "/consignees",
    summary="List consignees for the caller's branch",
)
def api_list_consignees(
    search:    str | None = Query(None, description="Filter by name (case-insensitive)"),
    is_active: bool       = Query(True),
    current_user: dict    = Depends(get_current_user),
):
    rows = list_consignees(
        company_id=current_user["company_id"],
        branch_id=current_user["branch_id"],
        search=search,
        is_active=is_active,
    )
    return {"count": len(rows), "consignees": rows}


@router.get(
    "/consignees/{consignee_id}",
    summary="Get a single consignee by ID",
)
def api_get_consignee(
    consignee_id: str,
    current_user: dict = Depends(get_current_user),
):
    row = get_consignee(consignee_id, current_user["company_id"])
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consignee not found")
    return row


@router.patch(
    "/consignees/{consignee_id}",
    summary="Update a consignee",
)
def api_update_consignee(
    consignee_id: str,
    body: ConsigneeUpdate,
    current_user: dict = Depends(get_current_user),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    data["updated_by"] = current_user["sub"]
    result = update_consignee(consignee_id, current_user["company_id"], data)
    return {"message": "Consignee updated.", "consignee": result}


@router.delete(
    "/consignees/{consignee_id}",
    summary="Soft-delete a consignee (sets is_active=False)",
)
def api_delete_consignee(
    consignee_id: str,
    current_user: dict = Depends(get_current_user),
):
    result = delete_consignee(consignee_id, current_user["company_id"], current_user["sub"])
    return {"message": "Consignee deactivated.", "consignee": result}


# ══════════════════════════════════════════════════════════════
# ROUTES — BILTY BOOK
# ══════════════════════════════════════════════════════════════

@router.post(
    "/books",
    status_code=201,
    summary="Create a new GR/LR number book",
)
def api_create_book(
    body: BookCreate,
    current_user: dict = Depends(get_current_user),
):
    body.validate_party_consistency() if hasattr(body, "validate_party_consistency") else None
    # Validate party_scope vs consignor/consignee IDs
    if body.party_scope == "CONSIGNOR" and not body.consignor_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "consignor_id required when party_scope is CONSIGNOR")
    if body.party_scope == "CONSIGNEE" and not body.consignee_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "consignee_id required when party_scope is CONSIGNEE")
    if body.party_scope == "COMMON" and (body.consignor_id or body.consignee_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "consignor_id and consignee_id must be null when party_scope is COMMON")

    data = body.model_dump()
    data["company_id"] = current_user["company_id"]
    data["branch_id"]  = _resolve_branch(current_user, data.pop("branch_id", None))
    data["created_by"] = current_user["sub"]
    data["updated_by"] = current_user["sub"]
    result = create_book(data)
    return {"message": "Bilty book created.", "book": result}


@router.get(
    "/books",
    summary="List GR/LR books. Super-admin sees all branches unless branch_id is supplied.",
)
def api_list_books(
    bilty_type:   str | None  = Query(None, pattern="^(REGULAR|MANUAL)$"),
    party_scope:  str | None  = Query(None, pattern="^(COMMON|CONSIGNOR|CONSIGNEE)$"),
    is_active:    bool        = Query(True),
    is_completed: bool | None = Query(None),
    branch_id:    str | None  = Query(None, description="Super-admin: filter by branch UUID. Omit to see all branches."),
    current_user: dict        = Depends(get_current_user),
):
    # Super-admin: use explicit branch_id filter if given, else None = all branches
    # Regular users: always scoped to their own branch
    effective_branch = _resolve_branch(current_user, branch_id) if branch_id else (
        None if current_user.get("post_in_office") == "super_admin" else current_user["branch_id"]
    )
    rows = list_books(
        company_id=current_user["company_id"],
        branch_id=effective_branch,
        bilty_type=bilty_type,
        party_scope=party_scope,
        is_active=is_active,
        is_completed=is_completed,
    )
    return {"count": len(rows), "books": rows}


# NOTE: /books/primary MUST be declared before /books/{book_id} so FastAPI
#       does not treat the literal string "primary" as a book_id path param.

@router.get(
    "/books/primary",
    summary="Get the primary bilty book for this branch (used for auto GR on bilty creation)",
)
def api_get_primary_book(
    bilty_type: str = Query("REGULAR", pattern="^(REGULAR|MANUAL)$"),
    current_user: dict = Depends(get_current_user),
):
    row = get_primary_book(current_user["company_id"], current_user["branch_id"], bilty_type)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No primary {bilty_type} book set for this branch")
    return row


@router.get(
    "/books/{book_id}",
    summary="Get a single bilty book by ID",
)
def api_get_book(
    book_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    row = get_book(str(book_id), current_user["company_id"])
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bilty book not found")
    return row


@router.patch(
    "/books/{book_id}",
    summary="Update a bilty book (meta / flags only — number range is immutable)",
)
def api_update_book(
    book_id: UUID,
    body: BookUpdate,
    current_user: dict = Depends(get_current_user),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    # Resolve branch_id for super_admin; strip it from the update payload
    # (branch is a filter key, not a field to patch arbitrarily)
    data.pop("branch_id", None)
    data["updated_by"] = current_user["sub"]
    result = update_book(str(book_id), current_user["company_id"], data)
    return {"message": "Bilty book updated.", "book": result}


@router.delete(
    "/books/{book_id}",
    summary="Soft-delete a bilty book (sets is_active=False). Issued GR numbers are not affected.",
)
def api_delete_book(
    book_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    result = delete_book(str(book_id), current_user["company_id"], current_user["sub"])
    return {"message": "Bilty book deactivated.", "book": result}


@router.patch(
    "/books/{book_id}/set-primary",
    summary="Mark a book as the primary book for its bilty_type in this branch",
)
def api_set_primary_book(
    book_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    book = get_book(str(book_id), current_user["company_id"])
    if not book:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bilty book not found")
    result = set_primary_book(
        str(book_id),
        current_user["company_id"],
        current_user["branch_id"],
        book["bilty_type"],
        current_user["sub"],
    )
    return {"message": f"Book set as primary {book['bilty_type']} book for this branch.", "book": result}


# ══════════════════════════════════════════════════════════════
# ROUTES — BILTY RATE
# ══════════════════════════════════════════════════════════════

@router.post(
    "/rates",
    status_code=201,
    summary="Create a rate card for a consignor or consignee",
)
def api_create_rate(
    body: RateCreate,
    current_user: dict = Depends(get_current_user),
):
    try:
        body.validate_party_consistency()
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    data = body.model_dump()
    data["company_id"] = current_user["company_id"]
    data["branch_id"]  = current_user["branch_id"]
    data["created_by"] = current_user["sub"]
    data["updated_by"] = current_user["sub"]
    result = create_rate(data)
    return {"message": "Bilty rate created.", "rate": result}


@router.get(
    "/rates",
    summary="List rate cards — filter by party_type, consignor, consignee, or city",
)
def api_list_rates(
    party_type:          str | None = Query(None, pattern="^(CONSIGNOR|CONSIGNEE)$"),
    consignor_id:        str | None = Query(None),
    consignee_id:        str | None = Query(None),
    destination_city_id: str | None = Query(None),
    is_active:           bool       = Query(True),
    current_user: dict              = Depends(get_current_user),
):
    rows = list_rates(
        company_id=current_user["company_id"],
        branch_id=current_user["branch_id"],
        party_type=party_type,
        consignor_id=consignor_id,
        consignee_id=consignee_id,
        destination_city_id=destination_city_id,
        is_active=is_active,
    )
    return {"count": len(rows), "rates": rows}


@router.get(
    "/rates/{rate_id}",
    summary="Get a single rate card by ID",
)
def api_get_rate(
    rate_id: str,
    current_user: dict = Depends(get_current_user),
):
    row = get_rate(rate_id, current_user["company_id"])
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rate not found")
    return row


@router.patch(
    "/rates/{rate_id}",
    summary="Update a rate card",
)
def api_update_rate(
    rate_id: str,
    body: RateUpdate,
    current_user: dict = Depends(get_current_user),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    data["updated_by"] = current_user["sub"]
    result = update_rate(rate_id, current_user["company_id"], data)
    return {"message": "Bilty rate updated.", "rate": result}


@router.delete(
    "/rates/{rate_id}",
    summary="Soft-delete a rate card (sets is_active=False)",
)
def api_delete_rate(
    rate_id: str,
    current_user: dict = Depends(get_current_user),
):
    result = delete_rate(rate_id, current_user["company_id"], current_user["sub"])
    return {"message": "Rate deactivated.", "rate": result}


# ════════════════════════════════════════════════════════════
# Pydantic models — Bilty Template
# ════════════════════════════════════════════════════════════

TEMPLATE_TYPES = "^(REGULAR_BILTY|MANUAL_BILTY|MONTHLY_CONSIGNOR|MONTHLY_CONSIGNEE)$"


class TemplateCreate(BaseModel):
    code:          str           = Field(..., min_length=1, max_length=50)
    name:          str           = Field(..., min_length=1, max_length=150)
    description:   str | None   = None
    slug:          str           = Field(..., min_length=1, max_length=100)
    # What document this template renders:
    #   REGULAR_BILTY     → normal book-based bilty
    #   MANUAL_BILTY      → manual / station bilty
    #   MONTHLY_CONSIGNOR → monthly consignment bill for consignor
    #   MONTHLY_CONSIGNEE → monthly consignment bill for consignee
    template_type: str           = Field("REGULAR_BILTY", pattern=TEMPLATE_TYPES)
    book_id:       str | None   = None  # optional: pin to a specific bilty book
    metadata:      dict[str, Any] = {}


class TemplateUpdate(BaseModel):
    code:          str | None   = Field(None, min_length=1, max_length=50)
    name:          str | None   = Field(None, min_length=1, max_length=150)
    description:   str | None   = None
    slug:          str | None   = Field(None, min_length=1, max_length=100)
    template_type: str | None   = Field(None, pattern=TEMPLATE_TYPES)
    book_id:       str | None   = None
    is_active:     bool | None  = None
    metadata:      dict[str, Any] | None = None


# ════════════════════════════════════════════════════════════
# Pydantic models — Bilty Discount
# ════════════════════════════════════════════════════════════

class DiscountCreate(BaseModel):
    discount_code:         str          = Field(..., min_length=1, max_length=50)
    percentage:            float        = Field(..., ge=0, le=100)
    bill_book_id:          str | None   = None
    max_amount_discounted: float | None = Field(None, ge=0)
    minimum_amount:        float        = Field(0.0, ge=0)


class DiscountUpdate(BaseModel):
    discount_code:         str | None   = Field(None, min_length=1, max_length=50)
    percentage:            float | None = Field(None, ge=0, le=100)
    bill_book_id:          str | None   = None
    max_amount_discounted: float | None = Field(None, ge=0)
    minimum_amount:        float | None = Field(None, ge=0)
    is_active:             bool | None  = None


# ════════════════════════════════════════════════════════════
# ROUTES — BILTY TEMPLATE
# ════════════════════════════════════════════════════════════

@router.post(
    "/templates",
    status_code=201,
    summary="Create a bilty print template",
)
def api_create_template(
    body: TemplateCreate,
    current_user: dict = Depends(get_current_user),
):
    data = body.model_dump()
    data["company_id"] = current_user["company_id"]
    data["branch_id"]  = current_user["branch_id"]
    data["created_by"] = current_user["sub"]
    data["updated_by"] = current_user["sub"]
    result = create_template(data)
    return {"message": "Template created.", "template": result}


@router.get(
    "/templates",
    summary="List bilty print templates for the caller's branch",
)
def api_list_templates(
    is_active:     bool       = Query(True),
    template_type: str | None = Query(None, pattern="^(REGULAR_BILTY|MANUAL_BILTY|MONTHLY_CONSIGNOR|MONTHLY_CONSIGNEE)$"),
    book_id:       str | None = Query(None, description="Filter templates pinned to a specific book"),
    current_user: dict = Depends(get_current_user),
):
    rows = list_templates(
        company_id=current_user["company_id"],
        branch_id=current_user["branch_id"],
        is_active=is_active,
        template_type=template_type,
        book_id=book_id,
    )
    return {"count": len(rows), "templates": rows}


# NOTE: /templates/primary MUST be declared before /templates/{template_id} so FastAPI
#       does not treat the literal string "primary" as a template_id path param.

@router.get(
    "/templates/primary",
    summary="Get the primary print template for this branch",
)
def api_get_primary_template(
    current_user: dict = Depends(get_current_user),
):
    row = get_primary_template(current_user["company_id"], current_user["branch_id"])
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No primary template set for this branch")
    return row


@router.get(
    "/templates/{template_id}",
    summary="Get a single bilty template by ID",
)
def api_get_template(
    template_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    row = get_template(str(template_id), current_user["company_id"])
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    return row


@router.patch(
    "/templates/{template_id}",
    summary="Update a bilty template",
)
def api_update_template(
    template_id: UUID,
    body: TemplateUpdate,
    current_user: dict = Depends(get_current_user),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    data["updated_by"] = current_user["sub"]
    result = update_template(str(template_id), current_user["company_id"], data)
    return {"message": "Template updated.", "template": result}


@router.delete(
    "/templates/{template_id}",
    summary="Soft-delete a bilty template (sets is_active=False)",
)
def api_delete_template(
    template_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    result = delete_template(str(template_id), current_user["company_id"], current_user["sub"])
    return {"message": "Template deactivated.", "template": result}


@router.patch(
    "/templates/{template_id}/set-primary",
    summary="Mark a template as the primary print template for this branch",
)
def api_set_primary_template(
    template_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    result = set_primary_template(
        str(template_id),
        current_user["company_id"],
        current_user["branch_id"],
        current_user["sub"],
    )
    return {"message": "Template set as primary for this branch.", "template": result}


# ════════════════════════════════════════════════════════════
# ROUTES — BILTY DISCOUNT
# ════════════════════════════════════════════════════════════

@router.post(
    "/discounts",
    status_code=201,
    summary="Create a discount record",
)
def api_create_discount(
    body: DiscountCreate,
    current_user: dict = Depends(get_current_user),
):
    data = body.model_dump()
    data["company_id"] = current_user["company_id"]
    data["branch_id"]  = current_user["branch_id"]
    data["created_by"] = current_user["sub"]
    data["updated_by"] = current_user["sub"]
    result = create_discount(data)
    return {"message": "Discount created.", "discount": result}


@router.get(
    "/discounts",
    summary="List discounts for the caller's branch",
)
def api_list_discounts(
    bill_book_id: str | None = Query(None, description="Filter by specific book UUID"),
    is_active:    bool       = Query(True),
    current_user: dict       = Depends(get_current_user),
):
    rows = list_discounts(
        company_id=current_user["company_id"],
        branch_id=current_user["branch_id"],
        bill_book_id=bill_book_id,
        is_active=is_active,
    )
    return {"count": len(rows), "discounts": rows}


@router.get(
    "/discounts/{discount_id}",
    summary="Get a single discount by ID",
)
def api_get_discount(
    discount_id: str,
    current_user: dict = Depends(get_current_user),
):
    row = get_discount(discount_id, current_user["company_id"])
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Discount not found")
    return row


@router.patch(
    "/discounts/{discount_id}",
    summary="Update a discount",
)
def api_update_discount(
    discount_id: str,
    body: DiscountUpdate,
    current_user: dict = Depends(get_current_user),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    data["updated_by"] = current_user["sub"]
    result = update_discount(discount_id, current_user["company_id"], data)
    return {"message": "Discount updated.", "discount": result}


@router.delete(
    "/discounts/{discount_id}",
    summary="Soft-delete a discount (sets is_active=False)",
)
def api_delete_discount(
    discount_id: str,
    current_user: dict = Depends(get_current_user),
):
    result = delete_discount(discount_id, current_user["company_id"], current_user["sub"])
    return {"message": "Discount deactivated.", "discount": result}
