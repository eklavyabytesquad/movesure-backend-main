"""
Company-wise EWB settings — CRUD for ewb_settings table.

The key field is `company_gstin` which becomes the `userGstin` parameter
on all NIC API calls.
"""
import logging

from app.services.utils.supabase import get_client

logger = logging.getLogger("movesure.ewaybill.settings")


def get_settings(company_id: str) -> dict | None:
    """Return ewb_settings row for the company, or None if not configured."""
    db = get_client()
    res = (
        db.table("ewb_settings")
        .select("*")
        .eq("company_id", company_id)
        .maybe_single()
        .execute()
    )
    return res.data if res.data else None


def get_settings_or_raise(company_id: str) -> dict:
    """Return settings or raise ValueError (caller converts to 404)."""
    row = get_settings(company_id)
    if not row:
        raise ValueError(
            f"EWB settings not configured for this company. "
            "Use POST /v1/ewaybill/settings to add your company GSTIN first."
        )
    return row


def get_company_gstin(company_id: str) -> str:
    """Convenience: return the stored company GSTIN or raise."""
    return get_settings_or_raise(company_id)["company_gstin"]


def upsert_settings(
    *,
    company_id: str,
    company_gstin: str,
    user_id: str,
) -> dict:
    """
    Create or update EWB settings for a company.
    Only sends the columns that are guaranteed to exist in the DB schema.
    mi_username is ALWAYS locked to the global Masters India account.
    """
    db = get_client()
    row = {
        "company_id":    company_id,
        "company_gstin": company_gstin.strip().upper(),
        "updated_by":    user_id,
    }
    res = (
        db.table("ewb_settings")
        .upsert({**row, "created_by": user_id}, on_conflict="company_id")
        .execute()
    )
    if not res.data:
        logger.warning("upsert_settings returned empty for company=%s", company_id)
        return row
    logger.info("EWB settings saved | company=%s gstin=%s", company_id, company_gstin)
    return res.data[0]


def delete_settings(company_id: str, user_id: str) -> None:
    """Update updated_by on deactivate; is_active handled if column exists."""
    db = get_client()
    (
        db.table("ewb_settings")
        .update({"updated_by": user_id})
        .eq("company_id", company_id)
        .execute()
    )
