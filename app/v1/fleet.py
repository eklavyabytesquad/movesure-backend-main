from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.middleware.auth import get_current_user
from app.services.fleet.service import (
    create_fleet,
    list_fleet,
    get_fleet,
    update_fleet,
    delete_fleet,
    assign_fleet_staff,
    create_fleet_staff,
    list_fleet_staff,
    get_fleet_staff,
    update_fleet_staff,
    delete_fleet_staff,
)

router = APIRouter(prefix="/fleet", tags=["Fleet"])


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic Models — Fleet Staff
# ──────────────────────────────────────────────────────────────────────────────

class FleetStaffCreate(BaseModel):
    name: str = Field(..., description="Full name of the staff member")
    role: str = Field(
        ...,
        description=(
            "Role of this person. One of:\n"
            "- **OWNER** — vehicle owner / fleet operator\n"
            "- **DRIVER** — primary driver assigned to trucks\n"
            "- **CONDUCTOR** — assistant / cleaner who travels with the truck\n"
            "- **CLEANER** — vehicle cleaner\n"
            "- **MECHANIC** — in-house mechanic for fleet maintenance"
        ),
    )
    branch_id: Optional[str] = Field(
        None,
        description="Branch this staff belongs to. Leave null for company-wide staff.",
    )
    mobile: Optional[str] = Field(None, description="Primary mobile number (10–15 digits)")
    alternate_mobile: Optional[str] = Field(None, description="Alternate / emergency mobile number")
    email: Optional[str] = Field(None, description="Email address")
    address: Optional[str] = Field(None, description="Residential / permanent address")

    # Govt IDs
    aadhar_no: Optional[str] = Field(None, description="12-digit Aadhaar number")
    pan_no: Optional[str] = Field(None, description="10-character PAN card number")

    # Driving license
    license_no: Optional[str] = Field(None, description="Driving license number (relevant for DRIVER role)")
    license_expiry: Optional[str] = Field(
        None,
        description="License expiry date in YYYY-MM-DD format. System tracks this for expiry alerts.",
    )
    license_type: Optional[str] = Field(
        None,
        description=(
            "License category:\n"
            "- **LMV** — Light Motor Vehicle\n"
            "- **HMV** — Heavy Motor Vehicle\n"
            "- **BOTH** — Valid for both LMV and HMV"
        ),
    )

    badge_no: Optional[str] = Field(None, description="Badge or employee ID number")
    date_of_birth: Optional[str] = Field(None, description="Date of birth in YYYY-MM-DD format")
    date_of_joining: Optional[str] = Field(None, description="Joining date in YYYY-MM-DD format")

    # Emergency
    emergency_contact_name: Optional[str] = Field(None, description="Name of emergency contact person")
    emergency_contact_mobile: Optional[str] = Field(None, description="Mobile number of emergency contact")

    # Bank
    bank_account_no: Optional[str] = Field(None, description="Bank account number for settlements")
    bank_ifsc: Optional[str] = Field(None, description="Bank IFSC code")
    bank_name: Optional[str] = Field(None, description="Bank name (e.g. 'HDFC Bank')")

    profile_photo_url: Optional[str] = Field(None, description="URL of profile photo (from file upload)")
    notes: Optional[str] = Field(None, description="Additional internal notes")
    metadata: Optional[dict] = Field(default_factory=dict, description="Extra key-value data for custom fields")


class FleetStaffUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Full name of the staff member")
    role: Optional[str] = Field(None, description="Role: OWNER / DRIVER / CONDUCTOR / CLEANER / MECHANIC")
    branch_id: Optional[str] = None
    mobile: Optional[str] = None
    alternate_mobile: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    aadhar_no: Optional[str] = None
    pan_no: Optional[str] = None
    license_no: Optional[str] = None
    license_expiry: Optional[str] = None
    license_type: Optional[str] = None
    badge_no: Optional[str] = None
    date_of_birth: Optional[str] = None
    date_of_joining: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_mobile: Optional[str] = None
    bank_account_no: Optional[str] = None
    bank_ifsc: Optional[str] = None
    bank_name: Optional[str] = None
    profile_photo_url: Optional[str] = None
    notes: Optional[str] = None
    metadata: Optional[dict] = None
    is_active: Optional[bool] = Field(None, description="Set to false to deactivate without deleting")


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic Models — Fleet (Vehicles)
# ──────────────────────────────────────────────────────────────────────────────

class FleetCreate(BaseModel):
    vehicle_no: str = Field(
        ...,
        description="Vehicle registration number in standard format (e.g. MH04AB1234). Must be unique per company.",
    )
    vehicle_type: Optional[str] = Field(
        "TRUCK",
        description=(
            "Type of vehicle:\n"
            "- **TRUCK** — standard goods truck\n"
            "- **TRAILER** — semi-trailer / full trailer\n"
            "- **MINI_TRUCK** — small commercial vehicle (e.g. Tata Ace, Mahindra Bolero Pickup)\n"
            "- **PICKUP** — pickup van\n"
            "- **TANKER** — liquid / gas tanker\n"
            "- **OTHER** — any other vehicle type"
        ),
    )
    branch_id: Optional[str] = Field(
        None,
        description="Branch this vehicle is primarily assigned to. Leave null for company-wide vehicles.",
    )

    # Vehicle details
    make: Optional[str] = Field(None, description="Manufacturer / make (e.g. 'TATA', 'ASHOK LEYLAND', 'MAHINDRA')")
    model: Optional[str] = Field(None, description="Vehicle model (e.g. '407', '1109', 'Prima')")
    year_of_manufacture: Optional[int] = Field(None, description="Year of manufacture (e.g. 2019)")
    body_type: Optional[str] = Field(
        None,
        description=(
            "Body type:\n"
            "- **OPEN** — open truck body\n"
            "- **CLOSED** — closed / covered body\n"
            "- **CONTAINER** — container body\n"
            "- **FLATBED** — flatbed / platform trailer\n"
            "- **TANKER** — tanker body\n"
            "- **OTHER** — other body type"
        ),
    )
    capacity_kg: Optional[float] = Field(None, description="Load capacity in kilograms (e.g. 10000 for 10 tons)")
    color: Optional[str] = Field(None, description="Vehicle color")
    engine_no: Optional[str] = Field(None, description="Engine number (from RC)")
    chassis_no: Optional[str] = Field(None, description="Chassis number (from RC)")

    # RC
    rc_no: Optional[str] = Field(None, description="Registration Certificate (RC) number")
    rc_expiry: Optional[str] = Field(
        None,
        description="RC expiry date in YYYY-MM-DD. System sends alerts before expiry.",
    )

    # Insurance
    insurance_no: Optional[str] = Field(None, description="Insurance policy number")
    insurance_company: Optional[str] = Field(None, description="Insurance company name (e.g. 'New India Assurance')")
    insurance_expiry: Optional[str] = Field(
        None,
        description="Insurance expiry date in YYYY-MM-DD. Critical — expired insurance = grounded vehicle.",
    )

    # Permit
    permit_no: Optional[str] = Field(None, description="National / State permit number")
    permit_type: Optional[str] = Field(
        None,
        description=(
            "Permit type:\n"
            "- **NATIONAL** — National Permit (valid across all states)\n"
            "- **STATE** — State Permit (valid within one state)\n"
            "- **LOCAL** — Local / City Permit"
        ),
    )
    permit_expiry: Optional[str] = Field(None, description="Permit expiry date in YYYY-MM-DD")

    # Fitness
    fitness_no: Optional[str] = Field(None, description="Fitness Certificate number")
    fitness_expiry: Optional[str] = Field(
        None,
        description="Fitness certificate expiry in YYYY-MM-DD. Mandatory for commercial vehicles.",
    )

    # PUC
    puc_no: Optional[str] = Field(None, description="PUC (Pollution Under Control) certificate number")
    puc_expiry: Optional[str] = Field(None, description="PUC expiry date in YYYY-MM-DD")

    # Assigned staff (optional at creation)
    current_owner_id: Optional[str] = Field(
        None,
        description="fleet_staff.staff_id of the current owner (role=OWNER)",
    )
    current_driver_id: Optional[str] = Field(
        None,
        description="fleet_staff.staff_id of the current primary driver (role=DRIVER)",
    )
    current_conductor_id: Optional[str] = Field(
        None,
        description="fleet_staff.staff_id of the current conductor/helper (role=CONDUCTOR)",
    )

    status: Optional[str] = Field(
        "ACTIVE",
        description=(
            "Vehicle status:\n"
            "- **ACTIVE** — available and road-worthy\n"
            "- **IN_TRANSIT** — currently on a trip\n"
            "- **MAINTENANCE** — under repair or scheduled service\n"
            "- **INACTIVE** — retired, sold, or grounded"
        ),
    )
    notes: Optional[str] = Field(None, description="Internal notes (service history, special remarks)")
    metadata: Optional[dict] = Field(default_factory=dict, description="Extra key-value data for custom fields")


class FleetUpdate(BaseModel):
    vehicle_no: Optional[str] = Field(None, description="Vehicle registration number")
    vehicle_type: Optional[str] = Field(None, description="TRUCK / TRAILER / MINI_TRUCK / PICKUP / TANKER / OTHER")
    branch_id: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year_of_manufacture: Optional[int] = None
    body_type: Optional[str] = None
    capacity_kg: Optional[float] = None
    color: Optional[str] = None
    engine_no: Optional[str] = None
    chassis_no: Optional[str] = None
    rc_no: Optional[str] = None
    rc_expiry: Optional[str] = None
    insurance_no: Optional[str] = None
    insurance_company: Optional[str] = None
    insurance_expiry: Optional[str] = None
    permit_no: Optional[str] = None
    permit_type: Optional[str] = None
    permit_expiry: Optional[str] = None
    fitness_no: Optional[str] = None
    fitness_expiry: Optional[str] = None
    puc_no: Optional[str] = None
    puc_expiry: Optional[str] = None
    current_owner_id: Optional[str] = None
    current_driver_id: Optional[str] = None
    current_conductor_id: Optional[str] = None
    status: Optional[str] = Field(None, description="ACTIVE / IN_TRANSIT / MAINTENANCE / INACTIVE")
    notes: Optional[str] = None
    metadata: Optional[dict] = None
    is_active: Optional[bool] = Field(None, description="Set to false to deactivate")


class AssignStaffRequest(BaseModel):
    owner_id: Optional[str] = Field(
        None,
        description=(
            "fleet_staff.staff_id to assign as current owner. "
            "Pass null to keep existing. Pass empty string '' to remove."
        ),
    )
    driver_id: Optional[str] = Field(
        None,
        description=(
            "fleet_staff.staff_id to assign as current driver. "
            "Pass null to keep existing. Pass empty string '' to remove."
        ),
    )
    conductor_id: Optional[str] = Field(
        None,
        description=(
            "fleet_staff.staff_id to assign as current conductor. "
            "Pass null to keep existing. Pass empty string '' to remove."
        ),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Fleet Staff Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/staff", summary="Create fleet staff")
def api_create_fleet_staff(body: FleetStaffCreate, user=Depends(get_current_user)):
    """
    Register a new fleet staff member (driver, owner, conductor, etc.).

    **Role guide:**
    - `OWNER` — vehicle owner / transport contractor
    - `DRIVER` — primary truck driver; fill license details
    - `CONDUCTOR` — cleaner / helper who travels with the driver
    - `CLEANER` — vehicle cleaner (yard-based)
    - `MECHANIC` — in-house mechanic

    **Document fields tracked for expiry alerts:**
    - `license_expiry` for drivers
    """
    payload = body.model_dump(exclude_none=True)
    payload["company_id"] = user["company_id"]
    return create_fleet_staff(payload)


@router.get("/staff", summary="List fleet staff")
def api_list_fleet_staff(
    role: Optional[str] = None,
    branch_id: Optional[str] = None,
    is_active: Optional[bool] = True,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user=Depends(get_current_user),
):
    """
    List fleet staff with optional filters.

    - `role` — filter by role: OWNER / DRIVER / CONDUCTOR / CLEANER / MECHANIC
    - `search` — partial name match
    - `is_active` — pass `false` to list deactivated staff
    """
    return list_fleet_staff(
        company_id=user["company_id"],
        branch_id=branch_id,
        role=role,
        is_active=is_active,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/staff/{staff_id}", summary="Get fleet staff detail")
def api_get_fleet_staff(staff_id: str, user=Depends(get_current_user)):
    """Retrieve full details of a single fleet staff member."""
    return get_fleet_staff(staff_id, user["company_id"])


@router.patch("/staff/{staff_id}", summary="Update fleet staff")
def api_update_fleet_staff(staff_id: str, body: FleetStaffUpdate, user=Depends(get_current_user)):
    """
    Partial update of a fleet staff record.

    All fields are optional — only supplied fields are updated.
    To deactivate a staff member, set `is_active: false`
    (preferred over DELETE so challan history is preserved).
    """
    payload = body.model_dump(exclude_none=True)
    payload["updated_by"] = user["sub"]
    return update_fleet_staff(staff_id, user["company_id"], payload)


@router.delete("/staff/{staff_id}", summary="Deactivate fleet staff")
def api_delete_fleet_staff(staff_id: str, user=Depends(get_current_user)):
    """
    Soft-delete (deactivate) a fleet staff member.

    Sets `is_active = false`. Existing challan and trip-sheet records
    that reference this staff are NOT affected.
    """
    return delete_fleet_staff(staff_id, user["company_id"], updated_by=user["sub"])


# ──────────────────────────────────────────────────────────────────────────────
# Fleet (Vehicle) Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.post("", summary="Register a fleet vehicle")
def api_create_fleet(body: FleetCreate, user=Depends(get_current_user)):
    """
    Register a new vehicle in the company fleet.

    **Document tracking** — the system tracks expiry dates for:
    - RC (`rc_expiry`)
    - Insurance (`insurance_expiry`)
    - Permit (`permit_expiry`)
    - Fitness certificate (`fitness_expiry`)
    - PUC (`puc_expiry`)

    **Assigned staff** — optionally link `current_driver_id`, `current_owner_id`,
    and `current_conductor_id` from your fleet_staff registry at creation time,
    or assign them later via `/fleet/{fleet_id}/assign`.

    Returns the created fleet record.
    """
    payload = body.model_dump(exclude_none=True)
    payload["company_id"] = user["company_id"]
    payload["created_by"] = user["sub"]
    return create_fleet(payload)


@router.get("", summary="List fleet vehicles")
def api_list_fleet(
    branch_id: Optional[str] = None,
    vehicle_type: Optional[str] = None,
    status: Optional[str] = None,
    is_active: Optional[bool] = True,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user=Depends(get_current_user),
):
    """
    List fleet vehicles with optional filters.

    Response includes **embedded staff objects** for
    `current_owner`, `current_driver`, and `current_conductor`
    so the frontend can show names without a second call.

    - `vehicle_type` — TRUCK / TRAILER / MINI_TRUCK / PICKUP / TANKER / OTHER
    - `status` — ACTIVE / IN_TRANSIT / MAINTENANCE / INACTIVE
    - `search` — partial vehicle number match
    """
    return list_fleet(
        company_id=user["company_id"],
        branch_id=branch_id,
        vehicle_type=vehicle_type,
        status=status,
        is_active=is_active,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/{fleet_id}", summary="Get fleet vehicle detail")
def api_get_fleet(fleet_id: str, user=Depends(get_current_user)):
    """
    Get full details of a fleet vehicle including all document fields
    and embedded staff info for current driver/owner/conductor.
    """
    return get_fleet(fleet_id, user["company_id"])


@router.patch("/{fleet_id}", summary="Update fleet vehicle")
def api_update_fleet(fleet_id: str, body: FleetUpdate, user=Depends(get_current_user)):
    """
    Partial update of a fleet vehicle record.

    All fields are optional. Use this to update document numbers, expiry dates,
    vehicle details, or status. To reassign driver/owner/conductor, prefer the
    dedicated `PATCH /fleet/{fleet_id}/assign` endpoint.
    """
    payload = body.model_dump(exclude_none=True)
    payload["updated_by"] = user["sub"]
    return update_fleet(fleet_id, user["company_id"], payload)


@router.patch("/{fleet_id}/assign", summary="Assign staff to fleet vehicle")
def api_assign_fleet_staff(fleet_id: str, body: AssignStaffRequest, user=Depends(get_current_user)):
    """
    Assign or replace the owner / driver / conductor on a fleet vehicle.

    - Pass a `fleet_staff.staff_id` to assign a person.
    - Pass `null` to leave the current assignment unchanged.
    - Pass `""` (empty string) to clear / unassign.

    All three fields are independently optional — you can update just the driver
    without touching the owner assignment.

    The fleet vehicle record's `current_owner_id`, `current_driver_id`, and
    `current_conductor_id` are updated. Existing challans that already used this
    vehicle are NOT retroactively changed.
    """
    return assign_fleet_staff(
        fleet_id=fleet_id,
        company_id=user["company_id"],
        updated_by=user["sub"],
        owner_id=body.owner_id,
        driver_id=body.driver_id,
        conductor_id=body.conductor_id,
    )


@router.delete("/{fleet_id}", summary="Deactivate fleet vehicle")
def api_delete_fleet(fleet_id: str, user=Depends(get_current_user)):
    """
    Soft-delete (deactivate) a fleet vehicle.

    Sets `is_active = false` and `status = INACTIVE`.
    Challan history that references this vehicle is NOT affected.
    """
    return delete_fleet(fleet_id, user["company_id"], updated_by=user["sub"])
