import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.services.utils.supabase import get_client

logger = logging.getLogger("movesure.bilty")


# ══════════════════════════════════════════════════════════════
# NEXT GR NUMBER  (atomic — calls DB function)
# ══════════════════════════════════════════════════════════════

def next_gr_no(book_id: str) -> dict:
    """
    Atomically claims the next GR number from a bilty_book row.
    Calls fn_next_gr_no(p_book_id) via Supabase RPC.
    Returns {"gr_no": "MUM/0042/25", "gr_number": 42}
    Raises 400 if book is exhausted / inactive, 500 on DB error.
    """
    logger.info("next_gr_no | book_id=%s", book_id)
    db = get_client()
    try:
        res = db.rpc("fn_next_gr_no", {"p_book_id": book_id}).execute()
    except Exception as exc:
        msg = str(exc)
        logger.warning("next_gr_no failed | book_id=%s | %s", book_id, msg)
        if "exhausted" in msg or "completed" in msg:
            raise HTTPException(status.HTTP_410_GONE, "Bilty book is exhausted — all numbers used")
        if "not available" in msg:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Bilty book not found or inactive")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)

    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "GR number generation returned no data")
    result = res.data[0]
    logger.info("next_gr_no ok | gr_no=%s gr_number=%s", result.get("gr_no"), result.get("gr_number"))
    return result


# ══════════════════════════════════════════════════════════════
# BILTY CRUD
# ══════════════════════════════════════════════════════════════

def create_bilty(data: dict) -> dict:
    logger.info("create_bilty | company=%s branch=%s gr_no=%s", data.get("company_id"), data.get("branch_id"), data.get("gr_no"))
    db = get_client()
    res = db.table("bilty").insert(data).execute()
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create bilty")
    logger.info("create_bilty ok | id=%s", res.data[0].get("bilty_id"))
    return res.data[0]


def list_bilties(
    company_id: str,
    branch_id: str,
    bilty_type: str | None = None,
    status_filter: str | None = None,
    payment_mode: str | None = None,
    consignor_id: str | None = None,
    consignee_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    is_active: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> list:
    db = get_client()
    q = (
        db.table("bilty")
        .select("*")
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("is_active", is_active)
        .order("bilty_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .offset(offset)
    )
    if bilty_type:
        q = q.eq("bilty_type", bilty_type)
    if status_filter:
        q = q.eq("status", status_filter)
    if payment_mode:
        q = q.eq("payment_mode", payment_mode)
    if consignor_id:
        q = q.eq("consignor_id", consignor_id)
    if consignee_id:
        q = q.eq("consignee_id", consignee_id)
    if from_date:
        q = q.gte("bilty_date", from_date)
    if to_date:
        q = q.lte("bilty_date", to_date)
    return q.execute().data or []


def get_bilty(bilty_id: str, company_id: str) -> dict | None:
    db = get_client()
    res = (
        db.table("bilty")
        .select("*")
        .eq("bilty_id", bilty_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def update_bilty(bilty_id: str, company_id: str, data: dict) -> dict:
    db = get_client()
    res = (
        db.table("bilty")
        .update(data)
        .eq("bilty_id", bilty_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bilty not found")
    return res.data[0]


def delete_bilty(
    bilty_id: str,
    company_id: str,
    deleted_by: str,
    deletion_reason: str,
) -> dict:
    """
    Soft-delete: is_active=False + full audit trail.
    Cancelled bilties are never hard-deleted.
    """
    now = datetime.now(timezone.utc).isoformat()
    return update_bilty(
        bilty_id,
        company_id,
        {
            "is_active":       False,
            "status":          "CANCELLED",
            "deleted_at":      now,
            "deleted_by":      deleted_by,
            "deletion_reason": deletion_reason,
            "updated_by":      deleted_by,
        },
    )
