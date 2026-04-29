from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from typing import Any

from app.middleware.auth import get_current_user
from app.services.iam.permissions import (
    create_permission, bulk_create_permissions,
    list_permissions, get_permission, update_permission, delete_permission,
    grant_permission, bulk_grant_permissions,
    list_user_permissions, list_permissions_for_company,
    revoke_permission, revoke_all_user_permissions,
)

router = APIRouter(prefix="/iam", tags=["IAM — Permissions"])


# ══════════════════════════════════════════════════════════════════════════════
# Pydantic models — Permission
# ══════════════════════════════════════════════════════════════════════════════

class PermissionCreate(BaseModel):
    module:    str            = Field(..., min_length=2, max_length=100, examples=["master", "staff", "reports"])
    action:    str            = Field(..., min_length=2, max_length=50,  examples=["create", "read", "update", "delete", "export"])
    scope:     str | None     = Field(None, max_length=50, examples=["company", "branch", "own"])
    slug:      str | None     = Field(None, max_length=150, examples=["master:city:create"])
    branch_id: str | None     = Field(None, description="Scope this permission to a specific branch (optional)")
    meta:      dict[str, Any] = {}
    is_active: bool           = True


class PermissionUpdate(BaseModel):
    module:    str | None            = Field(None, min_length=2, max_length=100)
    action:    str | None            = Field(None, min_length=2, max_length=50)
    scope:     str | None            = Field(None, max_length=50)
    slug:      str | None            = Field(None, max_length=150)
    branch_id: str | None            = None
    meta:      dict[str, Any] | None = None
    is_active: bool | None           = None


class PermissionBulkCreate(BaseModel):
    items: list[PermissionCreate] = Field(..., min_length=1, max_length=200)


# ══════════════════════════════════════════════════════════════════════════════
# Pydantic models — Grant
# ══════════════════════════════════════════════════════════════════════════════

class GrantRequest(BaseModel):
    user_id:       str
    permission_id: str
    branch_id:     str | None  = Field(None, description="Scope the grant to a specific branch")
    reason:        str | None  = None
    expires_at:    str | None  = Field(None, description="ISO 8601 expiry, e.g. 2026-12-31T23:59:59Z")


class BulkGrantItem(BaseModel):
    user_id:       str
    permission_id: str
    branch_id:     str | None = None
    reason:        str | None = None
    expires_at:    str | None = None


class BulkGrantRequest(BaseModel):
    items: list[BulkGrantItem] = Field(..., min_length=1, max_length=200)


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — PERMISSIONS
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/permissions",
    status_code=201,
    summary="Create a permission",
    description="Define a new permission for your company. `slug` is optional but recommended (e.g. `master:city:create`).",
)
def api_create_permission(body: PermissionCreate, current_user: dict = Depends(get_current_user)):
    company_id = current_user["company_id"]
    data = body.model_dump()
    result = create_permission(company_id, data, created_by=current_user.get("sub"))
    return {"message": "Permission created.", "permission": result}


@router.post(
    "/permissions/bulk",
    status_code=201,
    summary="Bulk create permissions",
)
def api_bulk_create_permissions(body: PermissionBulkCreate, current_user: dict = Depends(get_current_user)):
    company_id = current_user["company_id"]
    items = [i.model_dump() for i in body.items]
    return bulk_create_permissions(company_id, items, created_by=current_user.get("sub"))


@router.get(
    "/permissions",
    summary="List permissions",
    description="Returns all permissions for your company. Filter by `branch_id`, `module`, or `is_active`.",
)
def api_list_permissions(
    branch_id:    str | None  = Query(None),
    module:       str | None  = Query(None, description="Filter by module name"),
    is_active:    bool | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    perms = list_permissions(current_user["company_id"], branch_id, module, is_active)
    return {"count": len(perms), "permissions": perms}


@router.get(
    "/permissions/{permission_id}",
    summary="Get a permission",
)
def api_get_permission(permission_id: str, current_user: dict = Depends(get_current_user)):
    perm = get_permission(permission_id, current_user["company_id"])
    if not perm:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Permission '{permission_id}' not found.")
    return perm


@router.patch(
    "/permissions/{permission_id}",
    summary="Update a permission",
)
def api_update_permission(
    permission_id: str,
    body: PermissionUpdate,
    current_user: dict = Depends(get_current_user),
):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update.")
    result = update_permission(permission_id, current_user["company_id"], data, updated_by=current_user.get("sub"))
    return {"message": "Permission updated.", "permission": result}


@router.delete(
    "/permissions/{permission_id}",
    status_code=204,
    summary="Delete a permission",
    description="Deletes the permission and cascades to all user grants for it.",
)
def api_delete_permission(permission_id: str, current_user: dict = Depends(get_current_user)):
    delete_permission(permission_id, current_user["company_id"])


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — GRANT / REVOKE
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/grants",
    status_code=201,
    summary="Grant a permission to a user",
    description="Assign one permission to one user. Both user and permission must belong to your company.",
)
def api_grant_permission(body: GrantRequest, current_user: dict = Depends(get_current_user)):
    company_id = current_user["company_id"]
    granted_by = current_user.get("sub")
    data = body.model_dump(exclude={"user_id", "permission_id"}, exclude_none=True)
    result = grant_permission(company_id, body.user_id, body.permission_id, granted_by, data)
    return {"message": "Permission granted.", "grant": result}


@router.post(
    "/grants/bulk",
    status_code=201,
    summary="Bulk grant permissions",
    description="Grant multiple permissions to one or many users in a single call.",
)
def api_bulk_grant(body: BulkGrantRequest, current_user: dict = Depends(get_current_user)):
    company_id = current_user["company_id"]
    granted_by = current_user.get("sub")
    items = [i.model_dump(exclude_none=True) for i in body.items]
    return bulk_grant_permissions(company_id, granted_by, items)


@router.get(
    "/grants/company",
    summary="List all permission grants in the company",
    description="Returns who has which permissions company-wide. Filter by `branch_id`.",
)
def api_company_grants(
    branch_id:    str | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    grants = list_permissions_for_company(current_user["company_id"], branch_id)
    return {"count": len(grants), "grants": grants}


@router.get(
    "/grants/user/{user_id}",
    summary="List permissions granted to a user",
    description="Returns all permission grants for a specific user. Pass `active_only=true` to exclude inactive permissions.",
)
def api_user_grants(
    user_id:      str,
    branch_id:    str | None  = Query(None),
    active_only:  bool        = Query(False),
    current_user: dict = Depends(get_current_user),
):
    grants = list_user_permissions(user_id, current_user["company_id"], branch_id, active_only)
    return {"user_id": user_id, "count": len(grants), "grants": grants}


@router.delete(
    "/grants/{grant_id}",
    status_code=204,
    summary="Revoke a single permission grant",
)
def api_revoke_grant(grant_id: str, current_user: dict = Depends(get_current_user)):
    revoke_permission(grant_id, current_user["company_id"])


@router.delete(
    "/grants/user/{user_id}",
    summary="Revoke ALL permissions for a user",
    description="Removes every permission grant for the specified user within your company.",
)
def api_revoke_all_user_grants(user_id: str, current_user: dict = Depends(get_current_user)):
    count = revoke_all_user_permissions(user_id, current_user["company_id"])
    return {"message": f"Revoked {count} permission(s) for user '{user_id}'.", "revoked_count": count}
