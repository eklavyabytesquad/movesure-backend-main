import logging
from fastapi import HTTPException, status
from app.services.utils.supabase import get_client

logger = logging.getLogger("movesure.tenant")


def get_company_by_email(email: str) -> dict | None:
    db = get_client()
    res = db.table("tenant_companies").select("company_id,email").eq("email", email).limit(1).execute()
    return res.data[0] if res.data else None


def create_company(data: dict) -> dict:
    logger.info("create_company | name=%s", data.get("name"))
    db = get_client()
    res = db.table("tenant_companies").insert(data).execute()
    if not res.data:
        logger.error("create_company failed | data=%s", data)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create company")
    logger.info("create_company ok | id=%s", res.data[0].get("company_id"))
    return res.data[0]


def create_branch(data: dict) -> dict:
    logger.info("create_branch | name=%s company_id=%s", data.get("name"), data.get("company_id"))
    db = get_client()
    res = db.table("tenant_branches").insert(data).execute()
    if not res.data:
        logger.error("create_branch failed | data=%s", data)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create branch")
    logger.info("create_branch ok | id=%s", res.data[0].get("branch_id"))
    return res.data[0]


def get_branch_by_id(branch_id: str, company_id: str) -> dict | None:
    """Return a branch only if it belongs to the given company."""
    db = get_client()
    res = (
        db.table("tenant_branches")
        .select("branch_id,name,company_id,branch_code,branch_type")
        .eq("branch_id", branch_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def list_branches(company_id: str) -> list[dict]:
    """Return all branches belonging to a company, ordered by name."""
    db = get_client()
    res = (
        db.table("tenant_branches")
        .select("branch_id,name,branch_code,branch_type,address,metadata,created_at,updated_at")
        .eq("company_id", company_id)
        .order("name")
        .execute()
    )
    return res.data or []


def update_branch(branch_id: str, company_id: str, data: dict) -> dict:
    """Partially update a branch scoped to a company."""
    logger.info("update_branch | branch_id=%s", branch_id)
    db = get_client()
    res = (
        db.table("tenant_branches")
        .update(data)
        .eq("branch_id", branch_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Branch '{branch_id}' not found in your company.")
    return res.data[0]
