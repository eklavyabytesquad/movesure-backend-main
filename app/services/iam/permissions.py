import logging
from fastapi import HTTPException, status
from app.services.utils.supabase import get_client

logger = logging.getLogger("movesure.iam.permissions")

_PERM_FIELDS = "id,company_id,branch_id,module,action,scope,slug,meta,is_active,created_at,updated_at,created_by,updated_by"
_GRANT_FIELDS = "id,user_id,permission_id,company_id,branch_id,reason,granted_by,expires_at,created_at,updated_at"


# ══════════════════════════════════════════════════════════════════════════════
# PERMISSIONS (iam_permission)
# ══════════════════════════════════════════════════════════════════════════════

def create_permission(company_id: str, data: dict, created_by: str | None = None) -> dict:
    db = get_client()
    # slug uniqueness check
    if data.get("slug"):
        dup = db.table("iam_permission").select("id").eq("slug", data["slug"]).limit(1).execute()
        if dup.data:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Permission slug '{data['slug']}' already exists.")
    # module+action+scope uniqueness check (scoped to company)
    q = (
        db.table("iam_permission")
        .select("id")
        .eq("company_id", company_id)
        .eq("module", data["module"])
        .eq("action", data["action"])
    )
    if data.get("scope"):
        q = q.eq("scope", data["scope"])
    else:
        q = q.is_("scope", "null")
    if q.limit(1).execute().data:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Permission {data['module']}:{data['action']}:{data.get('scope', '*')} already exists for this company.",
        )

    row = {**data, "company_id": company_id}
    if created_by:
        row["created_by"] = created_by
        row["updated_by"] = created_by
    res = db.table("iam_permission").insert(row).execute()
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create permission.")
    logger.info("create_permission ok | id=%s slug=%s", res.data[0]["id"], res.data[0].get("slug"))
    return res.data[0]


def bulk_create_permissions(company_id: str, items: list[dict], created_by: str | None = None) -> dict:
    db = get_client()
    rows, errors = [], []
    for i, item in enumerate(items):
        if item.get("slug"):
            dup = db.table("iam_permission").select("id").eq("slug", item["slug"]).limit(1).execute()
            if dup.data:
                errors.append({"index": i, "slug": item["slug"], "error": "Duplicate slug."})
                continue
        row = {**item, "company_id": company_id}
        if created_by:
            row["created_by"] = created_by
            row["updated_by"] = created_by
        rows.append(row)

    created = []
    if rows:
        res = db.table("iam_permission").insert(rows).execute()
        created = res.data or []
    return {"created_count": len(created), "error_count": len(errors), "created": created, "errors": errors}


def list_permissions(
    company_id: str,
    branch_id: str | None = None,
    module: str | None = None,
    is_active: bool | None = None,
) -> list[dict]:
    db = get_client()
    q = (
        db.table("iam_permission")
        .select(_PERM_FIELDS)
        .eq("company_id", company_id)
        .order("module")
    )
    if branch_id:
        q = q.eq("branch_id", branch_id)
    if module:
        q = q.eq("module", module)
    if is_active is not None:
        q = q.eq("is_active", is_active)
    return q.execute().data or []


def get_permission(permission_id: str, company_id: str) -> dict | None:
    db = get_client()
    res = (
        db.table("iam_permission")
        .select(_PERM_FIELDS)
        .eq("id", permission_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def update_permission(permission_id: str, company_id: str, data: dict, updated_by: str | None = None) -> dict:
    db = get_client()
    if data.get("slug"):
        dup = (
            db.table("iam_permission")
            .select("id")
            .eq("slug", data["slug"])
            .neq("id", permission_id)
            .limit(1)
            .execute()
        )
        if dup.data:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Slug '{data['slug']}' is already used by another permission.")
    if updated_by:
        data["updated_by"] = updated_by
    res = (
        db.table("iam_permission")
        .update(data)
        .eq("id", permission_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Permission '{permission_id}' not found.")
    return res.data[0]


def delete_permission(permission_id: str, company_id: str) -> None:
    db = get_client()
    res = (
        db.table("iam_permission")
        .delete()
        .eq("id", permission_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Permission '{permission_id}' not found.")


# ══════════════════════════════════════════════════════════════════════════════
# GRANT / REVOKE (iam_user_permission)
# ══════════════════════════════════════════════════════════════════════════════

def grant_permission(
    company_id: str,
    user_id: str,
    permission_id: str,
    granted_by: str,
    data: dict,
) -> dict:
    db = get_client()
    # user must belong to company
    user_check = (
        db.table("iam_users")
        .select("id")
        .eq("id", user_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    if not user_check.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"User '{user_id}' not found in your company.")
    # permission must belong to company
    perm_check = (
        db.table("iam_permission")
        .select("id")
        .eq("id", permission_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    if not perm_check.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Permission '{permission_id}' not found in your company.")
    # duplicate check
    dup = (
        db.table("iam_user_permission")
        .select("id")
        .eq("user_id", user_id)
        .eq("permission_id", permission_id)
        .limit(1)
        .execute()
    )
    if dup.data:
        raise HTTPException(status.HTTP_409_CONFLICT, "User already has this permission.")

    row = {
        "user_id":       user_id,
        "permission_id": permission_id,
        "company_id":    company_id,
        "granted_by":    granted_by,
        "created_by":    granted_by,
        "updated_by":    granted_by,
        **data,
    }
    res = db.table("iam_user_permission").insert(row).execute()
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to grant permission.")
    logger.info("grant_permission ok | user=%s perm=%s", user_id, permission_id)
    return res.data[0]


def bulk_grant_permissions(company_id: str, granted_by: str, items: list[dict]) -> dict:
    """Grant multiple permissions to one or many users at once."""
    db = get_client()
    rows, errors = [], []

    for i, item in enumerate(items):
        user_id = item.get("user_id")
        permission_id = item.get("permission_id")

        if not user_id or not permission_id:
            errors.append({"index": i, "error": "Missing user_id or permission_id."})
            continue

        user_check = db.table("iam_users").select("id").eq("id", user_id).eq("company_id", company_id).limit(1).execute()
        if not user_check.data:
            errors.append({"index": i, "user_id": user_id, "error": "User not found in your company."})
            continue

        perm_check = db.table("iam_permission").select("id").eq("id", permission_id).eq("company_id", company_id).limit(1).execute()
        if not perm_check.data:
            errors.append({"index": i, "permission_id": permission_id, "error": "Permission not found in your company."})
            continue

        dup = db.table("iam_user_permission").select("id").eq("user_id", user_id).eq("permission_id", permission_id).limit(1).execute()
        if dup.data:
            errors.append({"index": i, "user_id": user_id, "permission_id": permission_id, "error": "Already granted."})
            continue

        rows.append({
            "user_id":       user_id,
            "permission_id": permission_id,
            "company_id":    company_id,
            "branch_id":     item.get("branch_id"),
            "reason":        item.get("reason"),
            "expires_at":    item.get("expires_at"),
            "granted_by":    granted_by,
            "created_by":    granted_by,
            "updated_by":    granted_by,
        })

    created = []
    if rows:
        res = db.table("iam_user_permission").insert(rows).execute()
        created = res.data or []
    return {"granted_count": len(created), "error_count": len(errors), "granted": created, "errors": errors}


def list_user_permissions(
    user_id: str,
    company_id: str,
    branch_id: str | None = None,
    active_only: bool = False,
) -> list[dict]:
    """List all permissions granted to a user, with optional branch filter."""
    db = get_client()
    q = (
        db.table("iam_user_permission")
        .select(f"{_GRANT_FIELDS},iam_permission(id,module,action,scope,slug,is_active)")
        .eq("user_id", user_id)
        .eq("company_id", company_id)
        .order("created_at", desc=True)
    )
    if branch_id:
        q = q.eq("branch_id", branch_id)
    rows = q.execute().data or []
    if active_only:
        rows = [r for r in rows if (r.get("iam_permission") or {}).get("is_active")]
    return rows


def list_permissions_for_company(
    company_id: str,
    branch_id: str | None = None,
) -> list[dict]:
    """List all grant rows for a whole company (who has what)."""
    db = get_client()
    q = (
        db.table("iam_user_permission")
        .select(f"{_GRANT_FIELDS},iam_permission(id,module,action,scope,slug)")
        .eq("company_id", company_id)
        .order("user_id")
    )
    if branch_id:
        q = q.eq("branch_id", branch_id)
    return q.execute().data or []


def revoke_permission(grant_id: str, company_id: str) -> None:
    db = get_client()
    res = (
        db.table("iam_user_permission")
        .delete()
        .eq("id", grant_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Grant '{grant_id}' not found.")
    logger.info("revoke_permission ok | grant_id=%s", grant_id)


def revoke_all_user_permissions(user_id: str, company_id: str) -> int:
    """Revoke every permission for a user. Returns deleted count."""
    db = get_client()
    res = (
        db.table("iam_user_permission")
        .delete()
        .eq("user_id", user_id)
        .eq("company_id", company_id)
        .execute()
    )
    count = len(res.data) if res.data else 0
    logger.info("revoke_all_permissions | user=%s count=%d", user_id, count)
    return count
