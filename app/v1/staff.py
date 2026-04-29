from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field

from app.middleware.auth import get_current_user
from app.services.auth.service import hash_password
from app.services.iam.service import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    list_staff,
    update_user,
)
from app.services.tenant.service import get_branch_by_id, list_branches

router = APIRouter(prefix="/staff", tags=["Staff Management"])


# ── Request / Response models ─────────────────────────────────

class AddStaffRequest(BaseModel):
    full_name:      str      = Field(..., min_length=2)
    email:          EmailStr
    password:       str      = Field(..., min_length=8)
    post_in_office: str      = Field(..., min_length=2, examples=["manager", "driver", "staff", "accountant"])
    branch_id:      str      = Field(..., description="UUID of the branch within your company")
    image_url:      str | None = None


class UpdateStaffRequest(BaseModel):
    full_name:      str | None = Field(None, min_length=2)
    post_in_office: str | None = Field(None, min_length=2)
    branch_id:      str | None = Field(None, description="Move staff to a different branch within the same company")
    image_url:      str | None = None
    is_active:      bool | None = None
    password:       str | None = Field(None, min_length=8, description="Set a new password")


# ── GET /v1/staff/branches — List branches for dropdown ──────

@router.get(
    "/branches",
    summary="List branches in your company",
    description="Returns all branches in the caller's company. Use this to populate a branch dropdown when adding or editing staff.",
)
def get_branches(current_user: dict = Depends(get_current_user)):
    company_id = current_user["company_id"]
    branches = list_branches(company_id)
    return {
        "company_id": company_id,
        "count":      len(branches),
        "branches":   branches,
    }


# ── POST /v1/staff — Add a new staff member ───────────────────

@router.post(
    "",
    status_code=201,
    summary="Add a staff member to a branch",
    description="Creates a new user account assigned to a branch within the caller's company. Requires a valid access token.",
)
def add_staff(
    body: AddStaffRequest,
    current_user: dict = Depends(get_current_user),
):
    company_id = current_user["company_id"]

    # 1. Verify the target branch belongs to the caller's company
    branch = get_branch_by_id(body.branch_id, company_id)
    if not branch:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Branch '{body.branch_id}' not found in your company.",
        )

    # 2. Email must be globally unique
    if get_user_by_email(body.email):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A user with email '{body.email}' already exists.",
        )

    # 3. Create the user
    user = create_user({
        "full_name":      body.full_name,
        "email":          body.email,
        "password":       hash_password(body.password),
        "post_in_office": body.post_in_office,
        "company_id":     company_id,
        "branch_id":      body.branch_id,
        "image_url":      body.image_url,
    })
    user.pop("password", None)

    return {
        "message": "Staff member added successfully.",
        "staff": user,
    }


# ── GET /v1/staff — List staff in the company ─────────────────

@router.get(
    "",
    summary="List staff members",
    description="Returns all staff in the caller's company. Filter by branch using `?branch_id=`.",
)
def get_staff_list(
    branch_id: str | None = Query(None, description="Filter by branch UUID"),
    current_user: dict = Depends(get_current_user),
):
    company_id = current_user["company_id"]

    # If filtering by branch, verify it belongs to the company
    if branch_id:
        branch = get_branch_by_id(branch_id, company_id)
        if not branch:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"Branch '{branch_id}' not found in your company.",
            )

    staff = list_staff(company_id, branch_id=branch_id)
    return {
        "company_id": company_id,
        "branch_id":  branch_id,
        "count":      len(staff),
        "staff":      staff,
    }


# ── GET /v1/staff/{user_id} — Get one staff member ───────────

@router.get(
    "/{user_id}",
    summary="Get a staff member by ID",
)
def get_staff_member(
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    company_id = current_user["company_id"]
    user = get_user_by_id(user_id, company_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found.")
    user.pop("password", None)
    return user


# ── PATCH /v1/staff/{user_id} — Update a staff member ────────

@router.patch(
    "/{user_id}",
    summary="Update a staff member",
    description="Update name, role, branch, image, active status, or password. Only provided fields are changed.",
)
def edit_staff(
    user_id: str,
    body: UpdateStaffRequest,
    current_user: dict = Depends(get_current_user),
):
    company_id = current_user["company_id"]

    # Ensure target user exists in this company
    existing = get_user_by_id(user_id, company_id)
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found.")

    # If moving to a different branch, validate it belongs to the same company
    if body.branch_id and body.branch_id != existing["branch_id"]:
        branch = get_branch_by_id(body.branch_id, company_id)
        if not branch:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"Branch '{body.branch_id}' not found in your company.",
            )

    # Build the update payload — only include explicitly provided fields
    changes: dict = {}
    if body.full_name      is not None: changes["full_name"]      = body.full_name
    if body.post_in_office is not None: changes["post_in_office"] = body.post_in_office
    if body.branch_id      is not None: changes["branch_id"]      = body.branch_id
    if body.image_url      is not None: changes["image_url"]      = body.image_url
    if body.is_active      is not None: changes["is_active"]      = body.is_active
    if body.password       is not None: changes["password"]       = hash_password(body.password)

    if not changes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No fields provided to update.")

    updated = update_user(user_id, company_id, changes)
    updated.pop("password", None)

    return {
        "message": "Staff member updated successfully.",
        "staff": updated,
    }
