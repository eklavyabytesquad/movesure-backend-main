import logging
from fastapi import HTTPException, status
from app.services.utils.supabase import get_client

logger = logging.getLogger("movesure.iam")


def create_user(data: dict) -> dict:
    logger.info("create_user | email=%s role=%s", data.get("email"), data.get("role"))
    db = get_client()
    res = db.table("iam_users").insert(data).execute()
    if not res.data:
        logger.error("create_user failed | email=%s", data.get("email"))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create user")
    logger.info("create_user ok | id=%s", res.data[0].get("id"))
    return res.data[0]


def get_user_by_email(email: str) -> dict | None:
    logger.info("get_user_by_email | email=%s", email)
    db = get_client()
    res = db.table("iam_users").select("*").eq("email", email).limit(1).execute()
    found = res.data[0] if res.data else None
    logger.info("get_user_by_email | found=%s", found is not None)
    return found


def get_user_by_id(user_id: str, company_id: str) -> dict | None:
    """Fetch a user only if they belong to the given company."""
    db = get_client()
    res = (
        db.table("iam_users")
        .select("id,email,full_name,image_url,post_in_office,company_id,branch_id,is_active,metadata,created_at,updated_at")
        .eq("id", user_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def list_staff(company_id: str, branch_id: str | None = None) -> list[dict]:
    """List all staff in a company, optionally filtered by branch."""
    logger.info("list_staff | company_id=%s branch_id=%s", company_id, branch_id)
    db = get_client()
    q = (
        db.table("iam_users")
        .select("id,email,full_name,image_url,post_in_office,company_id,branch_id,is_active,created_at,updated_at")
        .eq("company_id", company_id)
        .order("created_at", desc=True)
    )
    if branch_id:
        q = q.eq("branch_id", branch_id)
    res = q.execute()
    return res.data or []


def update_user(user_id: str, company_id: str, data: dict) -> dict:
    """Update a user record scoped to a company."""
    logger.info("update_user | user_id=%s", user_id)
    db = get_client()
    res = (
        db.table("iam_users")
        .update(data)
        .eq("id", user_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found")
    logger.info("update_user ok | user_id=%s", user_id)
    return res.data[0]
