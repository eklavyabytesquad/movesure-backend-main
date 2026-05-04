from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator

from app.middleware.auth import get_current_user
from app.services.challan.service import (
    # Template
    create_challan_template, list_challan_templates, get_challan_template,
    update_challan_template, delete_challan_template,
    get_primary_challan_template, set_primary_challan_template,
    # Book
    create_challan_book, list_challan_books, get_challan_book,
    update_challan_book, delete_challan_book,
    get_primary_challan_book, set_primary_challan_book, next_challan_no,
    get_book_for_route,
    # Trip Sheet
    create_trip_sheet, list_trip_sheets, get_trip_sheet_with_challans,
    list_trip_sheet_challans,
    update_trip_sheet, dispatch_trip_sheet, arrive_trip_sheet,
    # Challan
    create_challan, list_challans, get_challan_with_bilties, update_challan,
    get_primary_challan, set_primary_challan,
    dispatch_challan, arrive_hub_challan,
    add_bilty_to_challan, remove_bilty_from_challan,
    move_to_trip_sheet, remove_from_trip_sheet,
    list_challan_bilties, list_available_bilties, list_draft_bilties,
)

router = APIRouter(prefix="/challan", tags=["Challan"])


def _resolve_branch(user: dict, body_branch_id: str | None) -> str:
    """
    Super-admins may override branch_id via the request body.
    All other roles always use their own JWT branch.
    """
    if body_branch_id and user.get("post_in_office") == "super_admin":
        return body_branch_id
    return user["branch_id"]


# ══════════════════════════════════════════════════════════════
# Pydantic models — Template
# ══════════════════════════════════════════════════════════════

class ChallanTemplateCreate(BaseModel):
    code:          str  = Field(..., min_length=1, max_length=50)
    name:          str  = Field(..., min_length=1, max_length=150)
    description:   str | None = None
    slug:          str  = Field(..., min_length=1, max_length=100)
    template_type: str  = Field("CHALLAN", pattern="^(CHALLAN|SUMMARY|KAAT_RECEIPT|LOADING_CHALLAN)$")
    config:        dict[str, Any] = {}
    is_default:    bool = False
    is_active:     bool = True


class ChallanTemplateUpdate(BaseModel):
    name:          str | None = Field(None, min_length=1, max_length=150)
    description:   str | None = None
    config:        dict[str, Any] | None = None
    is_default:    bool | None = None
    is_active:     bool | None = None


# ══════════════════════════════════════════════════════════════
# Pydantic models — Book
# ══════════════════════════════════════════════════════════════

class ChallanBookCreate(BaseModel):
    # ── Identification ────────────────────────────────────────
    book_name:      str | None = Field(
        None, max_length=100,
        description="Human-readable label, e.g. 'FY25-26 Batch A'"
    )
    template_id:    str | None = Field(
        None,
        description="UUID of the challan_template used when printing from this book"
    )

    # ── Route scope ───────────────────────────────────────────
    route_scope:    str = Field(
        "OPEN",
        pattern="^(FIXED_ROUTE|OPEN)$",
        description=(
            "OPEN — book can be used for any destination. "
            "FIXED_ROUTE — book is tied to a specific from_branch → to_branch leg; "
            "both from_branch_id and to_branch_id are REQUIRED in that case."
        )
    )
    from_branch_id: str | None = Field(
        None,
        description="Required when route_scope=FIXED_ROUTE. UUID of the originating branch."
    )
    to_branch_id:   str | None = Field(
        None,
        description="Required when route_scope=FIXED_ROUTE. UUID of the destination branch."
    )

    # ── Number sequence ───────────────────────────────────────
    prefix:         str | None = Field(
        None, max_length=20,
        description="Optional prefix prepended to the number, e.g. 'MUM/'"
    )
    from_number:    int = Field(..., gt=0, description="First number in the series (inclusive)")
    to_number:      int = Field(..., gt=0, description="Last number in the series (inclusive)")
    digits:         int = Field(
        4, ge=1, le=10,
        description="Zero-pad width for the numeric part, e.g. 4 → '0001'"
    )
    postfix:        str | None = Field(
        None, max_length=20,
        description="Optional suffix appended after the number, e.g. '/25'"
    )

    # ── Behaviour ─────────────────────────────────────────────
    is_fixed:      bool = Field(
        False,
        description="If True the current_number never advances (same number re-used every time)"
    )
    auto_continue: bool = Field(
        False,
        description="If True a new book is auto-created when this one is exhausted"
    )
    is_primary:    bool = Field(
        False,
        description="Set True to make this the default book for the branch immediately"
    )
    metadata:      dict[str, Any] = Field(
        default={},
        description="Arbitrary key-value pairs for custom frontend/integration use"
    )
    # Super-admin only: create this book under a specific branch.
    # Regular users: this field is silently ignored.
    branch_id: str | None = Field(None, description="Super-admin: target branch UUID. Ignored for other roles.")

    @model_validator(mode="after")
    def validate_route_scope(self) -> "ChallanBookCreate":
        if self.route_scope == "FIXED_ROUTE":
            if not self.from_branch_id:
                raise ValueError(
                    "from_branch_id is required when route_scope is FIXED_ROUTE"
                )
            if not self.to_branch_id:
                raise ValueError(
                    "to_branch_id is required when route_scope is FIXED_ROUTE"
                )
        if self.from_number > self.to_number:
            raise ValueError(
                f"from_number ({self.from_number}) must be ≤ to_number ({self.to_number})"
            )
        return self


class ChallanBookUpdate(BaseModel):
    book_name:      str | None = Field(None, max_length=100)
    template_id:    str | None = Field(
        None, description="Change linked print template"
    )
    # Route can be corrected even after creation
    from_branch_id: str | None = Field(
        None, description="Update origin branch (only meaningful for FIXED_ROUTE books)"
    )
    to_branch_id:   str | None = Field(
        None, description="Update destination branch (only meaningful for FIXED_ROUTE books)"
    )
    is_fixed:      bool | None = None
    auto_continue: bool | None = None
    is_active:     bool | None = None
    is_primary:    bool | None = Field(
        None,
        description="Set True to promote this book to primary (prefer using the /set-primary endpoint)"
    )
    metadata:      dict[str, Any] | None = None
    # Super-admin only: reassign book to a different branch.
    branch_id: str | None = Field(None, description="Super-admin: target branch UUID. Ignored for other roles.")


# ══════════════════════════════════════════════════════════════
# Pydantic models — Trip Sheet
# ══════════════════════════════════════════════════════════════

class TripSheetCreate(BaseModel):
    trip_sheet_no:   str  = Field(..., min_length=1, max_length=50)
    transport_id:    str | None = None
    transport_name:  str | None = Field(None, max_length=255)
    transport_gstin: str | None = Field(None, max_length=15)
    from_city_id:    str | None = None
    to_city_id:      str | None = None
    vehicle_info:    dict[str, Any] = Field(default_factory=dict, description="Legacy/extra vehicle snapshot. Prefer fleet_id + driver_id.")
    # Fleet FK fields
    fleet_id:        str | None = Field(None, description="fleet.fleet_id — links this trip sheet to a registered vehicle")
    driver_id:       str | None = Field(None, description="fleet_staff.staff_id with role=DRIVER")
    owner_id:        str | None = Field(None, description="fleet_staff.staff_id with role=OWNER")
    conductor_id:    str | None = Field(None, description="fleet_staff.staff_id with role=CONDUCTOR")
    trip_date:       str | None = None
    remarks:         str | None = None
    metadata:        dict[str, Any] = {}


class TripSheetUpdate(BaseModel):
    transport_id:    str | None = None
    transport_name:  str | None = Field(None, max_length=255)
    transport_gstin: str | None = Field(None, max_length=15)
    from_city_id:    str | None = None
    to_city_id:      str | None = None
    vehicle_info:    dict[str, Any] | None = None
    # Fleet FK fields
    fleet_id:        str | None = Field(None, description="fleet.fleet_id")
    driver_id:       str | None = Field(None, description="fleet_staff.staff_id (DRIVER)")
    owner_id:        str | None = Field(None, description="fleet_staff.staff_id (OWNER)")
    conductor_id:    str | None = Field(None, description="fleet_staff.staff_id (CONDUCTOR)")
    trip_date:       str | None = None
    remarks:         str | None = None
    metadata:        dict[str, Any] | None = None
    is_active:       bool | None = None


# ══════════════════════════════════════════════════════════════
# Pydantic models — Challan
# ══════════════════════════════════════════════════════════════

class ChallanCreate(BaseModel):
    challan_no:      str | None = Field(None, max_length=50)  # omit to auto-claim from primary book
    book_id:         str | None = None
    trip_sheet_id:   str | None = None
    template_id:     str | None = None
    from_branch_id:  str | None = None
    to_branch_id:    str | None = None
    transport_id:    str | None = None
    transport_name:  str | None = Field(None, max_length=255)
    transport_gstin: str | None = Field(None, max_length=15)
    vehicle_info:    dict[str, Any] = Field(default_factory=dict, description="Legacy/extra vehicle snapshot. Prefer fleet_id + driver_id.")
    # Fleet FK fields
    fleet_id:        str | None = Field(None, description="fleet.fleet_id — links this challan to a registered vehicle")
    driver_id:       str | None = Field(None, description="fleet_staff.staff_id with role=DRIVER")
    owner_id:        str | None = Field(None, description="fleet_staff.staff_id with role=OWNER")
    conductor_id:    str | None = Field(None, description="fleet_staff.staff_id with role=CONDUCTOR")
    challan_date:    str | None = None
    remarks:         str | None = None
    is_primary:      bool       = False
    metadata:        dict[str, Any] = {}
    # Super-admin only: create this challan under a specific branch.
    # Regular users: this field is silently ignored.
    branch_id: str | None = Field(None, description="Super-admin: target branch UUID. Ignored for other roles.")


class ChallanUpdate(BaseModel):
    transport_id:    str | None = None
    transport_name:  str | None = Field(None, max_length=255)
    transport_gstin: str | None = Field(None, max_length=15)
    vehicle_info:    dict[str, Any] | None = None
    # Fleet FK fields
    fleet_id:        str | None = Field(None, description="fleet.fleet_id")
    driver_id:       str | None = Field(None, description="fleet_staff.staff_id (DRIVER)")
    owner_id:        str | None = Field(None, description="fleet_staff.staff_id (OWNER)")
    conductor_id:    str | None = Field(None, description="fleet_staff.staff_id (CONDUCTOR)")
    from_branch_id:  str | None = None
    to_branch_id:    str | None = None
    challan_date:    str | None = None
    remarks:         str | None = None
    pdf_url:         str | None = None
    metadata:        dict[str, Any] | None = None
    is_active:       bool | None = None


class AddBiltyRequest(BaseModel):
    bilty_id: str = Field(..., description="UUID of the bilty to add")


class MoveTripSheetRequest(BaseModel):
    trip_sheet_id: str = Field(..., description="UUID of the target trip sheet")


# ══════════════════════════════════════════════════════════════
# TEMPLATE ROUTES
# ══════════════════════════════════════════════════════════════

@router.post("/template", summary="Create challan template", status_code=status.HTTP_201_CREATED)
def api_create_challan_template(
    body: ChallanTemplateCreate,
    current_user: dict = Depends(get_current_user),
):
    data = body.model_dump()
    data["company_id"] = current_user["company_id"]
    data["branch_id"]  = current_user["branch_id"]
    data["created_by"] = current_user["sub"]
    data["updated_by"] = current_user["sub"]
    return create_challan_template(data)


@router.get("/template/primary", summary="Get primary/default template by type")
def api_get_primary_challan_template(
    template_type: str = Query("CHALLAN", pattern="^(CHALLAN|SUMMARY|KAAT_RECEIPT|LOADING_CHALLAN)$"),
    current_user: dict = Depends(get_current_user),
):
    tmpl = get_primary_challan_template(
        current_user["company_id"], current_user["branch_id"], template_type
    )
    if not tmpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            f"No primary template set for type {template_type}")
    return tmpl


@router.get("/template", summary="List challan templates")
def api_list_challan_templates(
    template_type: str | None = Query(None),
    is_active: bool = Query(True),
    current_user: dict = Depends(get_current_user),
):
    return list_challan_templates(
        current_user["company_id"], current_user["branch_id"], template_type, is_active
    )


@router.get("/template/{template_id}", summary="Get challan template by ID")
def api_get_challan_template(
    template_id: str,
    current_user: dict = Depends(get_current_user),
):
    tmpl = get_challan_template(template_id, current_user["company_id"])
    if not tmpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challan template not found")
    return tmpl


@router.put("/template/{template_id}", summary="Update challan template")
def api_update_challan_template(
    template_id: str,
    body: ChallanTemplateUpdate,
    current_user: dict = Depends(get_current_user),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    data["updated_by"] = current_user["sub"]
    return update_challan_template(template_id, current_user["company_id"], data)


@router.delete("/template/{template_id}", summary="Soft-delete challan template")
def api_delete_challan_template(
    template_id: str,
    current_user: dict = Depends(get_current_user),
):
    return delete_challan_template(template_id, current_user["company_id"], current_user["sub"])


@router.post("/template/{template_id}/set-primary",
             summary="Set template as primary/default for its type")
def api_set_primary_challan_template(
    template_id: str,
    current_user: dict = Depends(get_current_user),
):
    tmpl = get_challan_template(template_id, current_user["company_id"])
    if not tmpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challan template not found")
    return set_primary_challan_template(
        template_id,
        current_user["company_id"],
        current_user["branch_id"],
        tmpl["template_type"],
        current_user["sub"],
    )


# ══════════════════════════════════════════════════════════════
# BOOK ROUTES
# ══════════════════════════════════════════════════════════════

@router.post("/book", summary="Create challan book", status_code=status.HTTP_201_CREATED)
def api_create_challan_book(
    body: ChallanBookCreate,
    current_user: dict = Depends(get_current_user),
):
    data = body.model_dump()
    data["company_id"] = current_user["company_id"]
    data["branch_id"]  = _resolve_branch(current_user, data.pop("branch_id", None))
    data["created_by"] = current_user["sub"]
    data["updated_by"] = current_user["sub"]
    return create_challan_book(data)


@router.get("/book/primary", summary="Get primary challan book for current branch")
def api_get_primary_challan_book(
    current_user: dict = Depends(get_current_user),
):
    book = get_primary_challan_book(current_user["company_id"], current_user["branch_id"])
    if not book:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No primary challan book set for this branch")
    return book


@router.get("/book/next-no", summary="Claim next number from branch primary book")
def api_next_challan_no_primary(
    current_user: dict = Depends(get_current_user),
):
    book = get_primary_challan_book(current_user["company_id"], current_user["branch_id"])
    if not book:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No primary challan book set for this branch")
    return next_challan_no(book["book_id"])


@router.get(
    "/book/by-route",
    summary="Find active FIXED_ROUTE book for a specific origin → destination leg",
    description=(
        "Returns the active, non-exhausted FIXED_ROUTE challan book whose "
        "`from_branch_id` and `to_branch_id` match the supplied UUIDs. "
        "Useful when the frontend knows the dispatch leg and needs to pre-fill the challan number."
    ),
)
def api_get_book_for_route(
    from_branch_id: str = Query(..., description="UUID of the originating branch"),
    to_branch_id:   str = Query(..., description="UUID of the destination branch"),
    current_user: dict = Depends(get_current_user),
):
    book = get_book_for_route(
        current_user["company_id"], from_branch_id, to_branch_id
    )
    if not book:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No active FIXED_ROUTE book found for the specified from_branch → to_branch leg",
        )
    return book


@router.get(
    "/book",
    summary="List challan books. Super-admin sees all branches unless branch_id is supplied.",
    description=(
        "List books scoped to the current branch. "
        "Use `route_scope=FIXED_ROUTE` + `from_branch_id` / `to_branch_id` to narrow to a specific leg."
    ),
)
def api_list_challan_books(
    route_scope:    str | None  = Query(None, pattern="^(FIXED_ROUTE|OPEN)$",
                                        description="Filter by route scope"),
    from_branch_id: str | None  = Query(None, description="Filter FIXED_ROUTE books by origin branch UUID"),
    to_branch_id:   str | None  = Query(None, description="Filter FIXED_ROUTE books by destination branch UUID"),
    is_active:      bool        = Query(True,  description="Return only active (non-deleted) books"),
    is_completed:   bool | None = Query(None,  description="True = exhausted books only; False = books with remaining numbers"),
    is_primary:     bool | None = Query(None,  description="True = only the primary book for this branch"),
    branch_id:      str | None  = Query(None, description="Super-admin: filter by branch UUID. Omit to see all branches."),
    current_user: dict = Depends(get_current_user),
):
    # Super-admin: explicit branch_id filter if given, else None = all branches
    # Regular users: always scoped to their own branch
    effective_branch = _resolve_branch(current_user, branch_id) if branch_id else (
        None if current_user.get("post_in_office") == "super_admin" else current_user["branch_id"]
    )
    return list_challan_books(
        current_user["company_id"], effective_branch,
        route_scope, from_branch_id, to_branch_id, is_active, is_completed, is_primary,
    )


@router.get("/book/{book_id}", summary="Get challan book by ID")
def api_get_challan_book(
    book_id: str,
    current_user: dict = Depends(get_current_user),
):
    book = get_challan_book(book_id, current_user["company_id"])
    if not book:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challan book not found")
    return book


@router.get("/book/{book_id}/next-no", summary="Claim next number from specific book")
def api_next_challan_no_book(
    book_id: str,
    current_user: dict = Depends(get_current_user),
):
    return next_challan_no(book_id)


@router.put("/book/{book_id}", summary="Update challan book")
def api_update_challan_book(
    book_id: str,
    body: ChallanBookUpdate,
    current_user: dict = Depends(get_current_user),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    data.pop("branch_id", None)  # branch_id is a filter key, not patchable after creation
    data["updated_by"] = current_user["sub"]
    return update_challan_book(book_id, current_user["company_id"], data)


@router.delete("/book/{book_id}", summary="Soft-delete challan book")
def api_delete_challan_book(
    book_id: str,
    current_user: dict = Depends(get_current_user),
):
    return delete_challan_book(book_id, current_user["company_id"], current_user["sub"])


@router.post("/book/{book_id}/set-primary",
             summary="Set book as primary for current branch")
def api_set_primary_challan_book(
    book_id: str,
    current_user: dict = Depends(get_current_user),
):
    return set_primary_challan_book(
        book_id, current_user["company_id"], current_user["branch_id"], current_user["sub"]
    )


# ══════════════════════════════════════════════════════════════
# TRIP SHEET ROUTES
# ══════════════════════════════════════════════════════════════

@router.post("/trip-sheet", summary="Create trip sheet", status_code=status.HTTP_201_CREATED)
def api_create_trip_sheet(
    body: TripSheetCreate,
    current_user: dict = Depends(get_current_user),
):
    data = body.model_dump(exclude_none=True)
    data["company_id"] = current_user["company_id"]
    data["created_by"] = current_user["sub"]
    data["updated_by"] = current_user["sub"]
    return create_trip_sheet(data)


@router.get("/trip-sheet", summary="List trip sheets")
def api_list_trip_sheets(
    trip_status: str | None = Query(None, pattern="^(DRAFT|OPEN|DISPATCHED|ARRIVED|CLOSED)$"),
    from_date:   str | None = Query(None),
    to_date:     str | None = Query(None),
    is_active:   bool       = Query(True),
    limit:       int        = Query(50, ge=1, le=200),
    offset:      int        = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    return list_trip_sheets(
        current_user["company_id"], trip_status, from_date, to_date, is_active, limit, offset
    )


@router.get("/trip-sheet/{trip_sheet_id}", summary="Get trip sheet with its challans")
def api_get_trip_sheet(
    trip_sheet_id: str,
    current_user: dict = Depends(get_current_user),
):
    sheet = get_trip_sheet_with_challans(trip_sheet_id, current_user["company_id"])
    if not sheet:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip sheet not found")
    return sheet


@router.get(
    "/trip-sheet/{trip_sheet_id}/challans",
    summary="List all challans in a trip sheet (cross-branch view)",
)
def api_trip_sheet_challans(
    trip_sheet_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Returns every challan attached to this trip sheet, across all branches.
    Each challan includes:
    - `is_mine`: true when the challan belongs to the current user's branch
    - `bilties`: lightweight list of bilties on that challan

    Use this on the Trip Sheet detail page so Branch B can see
    Branch A's challan (and vice versa) within the same truck trip.
    """
    return list_trip_sheet_challans(
        trip_sheet_id,
        current_user["company_id"],
        viewing_branch_id=current_user["branch_id"],
    )


@router.put("/trip-sheet/{trip_sheet_id}", summary="Update trip sheet")
def api_update_trip_sheet(
    trip_sheet_id: str,
    body: TripSheetUpdate,
    current_user: dict = Depends(get_current_user),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    data["updated_by"] = current_user["sub"]
    return update_trip_sheet(trip_sheet_id, current_user["company_id"], data)


@router.post("/trip-sheet/{trip_sheet_id}/dispatch", summary="Dispatch trip sheet")
def api_dispatch_trip_sheet(
    trip_sheet_id: str,
    current_user: dict = Depends(get_current_user),
):
    return dispatch_trip_sheet(trip_sheet_id, current_user["company_id"], current_user["sub"])


@router.post("/trip-sheet/{trip_sheet_id}/arrive", summary="Mark trip sheet as arrived")
def api_arrive_trip_sheet(
    trip_sheet_id: str,
    current_user: dict = Depends(get_current_user),
):
    return arrive_trip_sheet(trip_sheet_id, current_user["company_id"], current_user["sub"])


# ══════════════════════════════════════════════════════════════
# CHALLAN ROUTES
# NOTE: Static paths (/primary, /available-bilties) MUST be
#       declared BEFORE /{challan_id} so FastAPI matches correctly.
# ══════════════════════════════════════════════════════════════

@router.post("", summary="Create challan", status_code=status.HTTP_201_CREATED)
def api_create_challan(
    body: ChallanCreate,
    current_user: dict = Depends(get_current_user),
):
    data = body.model_dump(exclude_none=True)
    company_id = current_user["company_id"]
    branch_id  = _resolve_branch(current_user, data.pop("branch_id", None))
    user_id    = current_user["sub"]

    # Auto-claim challan number from primary book if not provided
    if not data.get("challan_no"):
        book_id = data.get("book_id")
        if not book_id:
            primary_book = get_primary_challan_book(company_id, branch_id)
            if not primary_book:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Provide challan_no or set a primary challan book for this branch",
                )
            book_id = primary_book["book_id"]
            data["book_id"] = book_id
        result = next_challan_no(book_id)
        data["challan_no"] = result["challan_no"]

    data["company_id"] = company_id
    data["branch_id"]  = branch_id
    data["created_by"] = user_id
    data["updated_by"] = user_id
    return create_challan(data)


@router.get("/primary", summary="Get primary (active) challan for current branch")
def api_get_primary_challan(
    current_user: dict = Depends(get_current_user),
):
    challan = get_primary_challan(current_user["company_id"], current_user["branch_id"])
    if not challan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No primary challan set for this branch")
    return challan


@router.get("/available-bilties", summary="List SAVED bilties not yet assigned to any challan")
def api_available_bilties(
    to_city_id: str | None = Query(None, description="Filter by destination city"),
    from_date:  str | None = Query(None, description="ISO date YYYY-MM-DD"),
    to_date:    str | None = Query(None, description="ISO date YYYY-MM-DD"),
    limit:      int        = Query(100, ge=1, le=500),
    offset:     int        = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    return list_available_bilties(
        current_user["company_id"], current_user["branch_id"],
        to_city_id, from_date, to_date, limit, offset,
    )


@router.get("/draft-bilties", summary="List DRAFT bilties for current branch")
def api_draft_bilties(
    from_date: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    to_date:   str | None = Query(None, description="ISO date YYYY-MM-DD"),
    limit:     int        = Query(100, ge=1, le=500),
    offset:    int        = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    return list_draft_bilties(
        current_user["company_id"], current_user["branch_id"],
        from_date, to_date, limit, offset,
    )


@router.get("", summary="List challans")
def api_list_challans(
    challan_status: str | None = Query(None, pattern="^(DRAFT|OPEN|DISPATCHED|ARRIVED_HUB|CLOSED)$"),
    from_date:      str | None = Query(None),
    to_date:        str | None = Query(None),
    trip_sheet_id:  str | None = Query(None),
    is_active:      bool       = Query(True),
    limit:          int        = Query(50, ge=1, le=200),
    offset:         int        = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    return list_challans(
        current_user["company_id"], current_user["branch_id"],
        challan_status, from_date, to_date, trip_sheet_id, is_active, limit, offset,
    )


@router.get("/{challan_id}", summary="Get challan with its bilties")
def api_get_challan(
    challan_id: str,
    current_user: dict = Depends(get_current_user),
):
    challan = get_challan_with_bilties(challan_id, current_user["company_id"])
    if not challan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challan not found")
    return challan


@router.put("/{challan_id}", summary="Update challan details")
def api_update_challan(
    challan_id: str,
    body: ChallanUpdate,
    current_user: dict = Depends(get_current_user),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    data["updated_by"] = current_user["sub"]
    return update_challan(challan_id, current_user["company_id"], data)


@router.post("/{challan_id}/set-primary",
             summary="Set challan as primary for current branch")
def api_set_primary_challan(
    challan_id: str,
    current_user: dict = Depends(get_current_user),
):
    return set_primary_challan(
        challan_id, current_user["company_id"], current_user["branch_id"], current_user["sub"]
    )


@router.post("/{challan_id}/dispatch", summary="Dispatch challan (and all its bilties)")
def api_dispatch_challan(
    challan_id: str,
    current_user: dict = Depends(get_current_user),
):
    return dispatch_challan(challan_id, current_user["company_id"], current_user["sub"])


@router.post("/{challan_id}/arrive-hub",
             summary="Mark challan arrived at hub (and all its bilties)")
def api_arrive_hub_challan(
    challan_id: str,
    current_user: dict = Depends(get_current_user),
):
    return arrive_hub_challan(challan_id, current_user["company_id"], current_user["sub"])


@router.get("/{challan_id}/bilties", summary="List all bilties on a challan")
def api_list_challan_bilties(
    challan_id: str,
    current_user: dict = Depends(get_current_user),
):
    return list_challan_bilties(challan_id, current_user["company_id"])


@router.post("/{challan_id}/add-bilty", summary="Add a bilty to this challan")
def api_add_bilty_to_challan(
    challan_id: str,
    body: AddBiltyRequest,
    current_user: dict = Depends(get_current_user),
):
    return add_bilty_to_challan(
        challan_id, body.bilty_id, current_user["company_id"], current_user["sub"]
    )


@router.post("/{challan_id}/remove-bilty/{bilty_id}",
             summary="Remove a bilty from this challan")
def api_remove_bilty_from_challan(
    challan_id: str,
    bilty_id: str,
    current_user: dict = Depends(get_current_user),
):
    return remove_bilty_from_challan(
        challan_id, bilty_id, current_user["company_id"], current_user["sub"]
    )


@router.post("/{challan_id}/move-to-trip-sheet",
             summary="Assign this challan to a trip sheet")
def api_move_to_trip_sheet(
    challan_id: str,
    body: MoveTripSheetRequest,
    current_user: dict = Depends(get_current_user),
):
    return move_to_trip_sheet(
        challan_id, body.trip_sheet_id, current_user["company_id"], current_user["sub"]
    )


@router.post("/{challan_id}/remove-from-trip-sheet",
             summary="Remove this challan from its current trip sheet")
def api_remove_from_trip_sheet(
    challan_id: str,
    current_user: dict = Depends(get_current_user),
):
    return remove_from_trip_sheet(challan_id, current_user["company_id"], current_user["sub"])
