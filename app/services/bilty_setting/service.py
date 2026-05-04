import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.services.utils.supabase import get_client

logger = logging.getLogger("movesure.bilty_setting")


# ══════════════════════════════════════════════════════════════
# CONSIGNOR
# ══════════════════════════════════════════════════════════════

def create_consignor(data: dict) -> dict:
    logger.info("create_consignor | company=%s branch=%s", data.get("company_id"), data.get("branch_id"))
    db = get_client()
    res = db.table("bilty_consignor").insert(data).execute()
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create consignor")
    logger.info("create_consignor ok | id=%s", res.data[0].get("consignor_id"))
    return res.data[0]


def list_consignors(
    company_id: str,
    branch_id: str,
    search: str | None = None,
    is_active: bool = True,
) -> list:
    db = get_client()
    q = (
        db.table("bilty_consignor")
        .select("*")
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("is_active", is_active)
        .order("created_at", desc=True)
    )
    if search:
        q = q.ilike("consignor_name", f"%{search}%")
    return q.execute().data or []


def get_consignor(consignor_id: str, company_id: str) -> dict | None:
    db = get_client()
    res = (
        db.table("bilty_consignor")
        .select("*")
        .eq("consignor_id", consignor_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def update_consignor(consignor_id: str, company_id: str, data: dict) -> dict:
    db = get_client()
    res = (
        db.table("bilty_consignor")
        .update(data)
        .eq("consignor_id", consignor_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consignor not found")
    return res.data[0]


def delete_consignor(consignor_id: str, company_id: str, updated_by: str) -> dict:
    """Soft-delete: set is_active=False."""
    return update_consignor(
        consignor_id,
        company_id,
        {"is_active": False, "updated_by": updated_by},
    )


# ══════════════════════════════════════════════════════════════
# CONSIGNEE
# ══════════════════════════════════════════════════════════════

def create_consignee(data: dict) -> dict:
    logger.info("create_consignee | company=%s branch=%s", data.get("company_id"), data.get("branch_id"))
    db = get_client()
    res = db.table("bilty_consignee").insert(data).execute()
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create consignee")
    logger.info("create_consignee ok | id=%s", res.data[0].get("consignee_id"))
    return res.data[0]


def list_consignees(
    company_id: str,
    branch_id: str,
    search: str | None = None,
    is_active: bool = True,
) -> list:
    db = get_client()
    q = (
        db.table("bilty_consignee")
        .select("*")
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("is_active", is_active)
        .order("created_at", desc=True)
    )
    if search:
        q = q.ilike("consignee_name", f"%{search}%")
    return q.execute().data or []


def get_consignee(consignee_id: str, company_id: str) -> dict | None:
    db = get_client()
    res = (
        db.table("bilty_consignee")
        .select("*")
        .eq("consignee_id", consignee_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def update_consignee(consignee_id: str, company_id: str, data: dict) -> dict:
    db = get_client()
    res = (
        db.table("bilty_consignee")
        .update(data)
        .eq("consignee_id", consignee_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consignee not found")
    return res.data[0]


def delete_consignee(consignee_id: str, company_id: str, updated_by: str) -> dict:
    """Soft-delete: set is_active=False."""
    return update_consignee(
        consignee_id,
        company_id,
        {"is_active": False, "updated_by": updated_by},
    )


# ══════════════════════════════════════════════════════════════
# BILTY BOOK
# ══════════════════════════════════════════════════════════════

def peek_gr_no(book_id: str, company_id: str) -> dict:
    """
    Read-only preview of the next GR number for a book.
    Does NOT increment current_number — safe to call on every book selection.
    Returns:
        gr_no       — formatted string e.g. "MUM/0042/25"
        gr_number   — raw integer e.g. 42
        book_id
        book_name
        bilty_type  — "REGULAR" | "MANUAL"
        is_exhausted — True when current_number >= to_number (for ranged books)
    """
    book = get_book(book_id, company_id)
    if not book:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bilty book not found")
    if not book.get("is_active"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bilty book is inactive")

    current = book.get("current_number")
    from_no = book.get("from_number")
    to_no   = book.get("to_number")

    # No series defined (MANUAL book without a range)
    if current is None and from_no is None:
        return {
            "gr_no":       None,
            "gr_number":   None,
            "book_id":     book_id,
            "book_name":   book.get("book_name"),
            "bilty_type":  book.get("bilty_type"),
            "is_exhausted": False,
            "has_series":  False,
        }

    # Next number to be issued
    if current is None:
        next_num = from_no
    else:
        next_num = current + 1

    is_exhausted = bool(to_no and next_num > to_no)

    # Format: prefix + zero-padded number + postfix
    digits  = book.get("digits") or 4
    prefix  = book.get("prefix") or ""
    postfix = book.get("postfix") or ""
    gr_no   = f"{prefix}{str(next_num).zfill(digits)}{postfix}" if not is_exhausted else None

    return {
        "gr_no":       gr_no,
        "gr_number":   next_num if not is_exhausted else None,
        "book_id":     book_id,
        "book_name":   book.get("book_name"),
        "bilty_type":  book.get("bilty_type"),
        "is_exhausted": is_exhausted,
        "has_series":  True,
    }


def create_book(data: dict) -> dict:
    logger.info("create_book | company=%s branch=%s type=%s", data.get("company_id"), data.get("branch_id"), data.get("bilty_type"))
    # current_number must start at from_number
    if "current_number" not in data and "from_number" in data:
        data["current_number"] = data["from_number"]
    db = get_client()
    res = db.table("bilty_book").insert(data).execute()
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create bilty book")
    logger.info("create_book ok | id=%s", res.data[0].get("book_id"))
    return res.data[0]


def list_books(
    company_id: str,
    branch_id: str | None,
    bilty_type: str | None = None,
    party_scope: str | None = None,
    is_active: bool = True,
    is_completed: bool | None = None,
) -> list:
    db = get_client()
    q = (
        db.table("bilty_book")
        .select("*")
        .eq("company_id", company_id)
        .eq("is_active", is_active)
        .order("created_at", desc=True)
    )
    if branch_id:
        q = q.eq("branch_id", branch_id)
    if bilty_type:
        q = q.eq("bilty_type", bilty_type)
    if party_scope:
        q = q.eq("party_scope", party_scope)
    if is_completed is not None:
        q = q.eq("is_completed", is_completed)
    return q.execute().data or []


def get_book(book_id: str, company_id: str) -> dict | None:
    db = get_client()
    res = (
        db.table("bilty_book")
        .select("*")
        .eq("book_id", book_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def update_book(book_id: str, company_id: str, data: dict) -> dict:
    db = get_client()
    res = (
        db.table("bilty_book")
        .update(data)
        .eq("book_id", book_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bilty book not found")
    return res.data[0]


def delete_book(book_id: str, company_id: str, updated_by: str) -> dict:
    """Soft-delete: set is_active=False. Does not remove issued GR numbers."""
    return update_book(
        book_id,
        company_id,
        {"is_active": False, "updated_by": updated_by},
    )


def get_primary_book(company_id: str, branch_id: str, bilty_type: str = "REGULAR") -> dict | None:
    """Return the primary active book for a branch + bilty_type, or None."""
    db = get_client()
    res = (
        db.table("bilty_book")
        .select("*")
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("bilty_type", bilty_type)
        .eq("is_primary", True)
        .eq("is_active", True)
        .eq("is_completed", False)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def set_primary_book(book_id: str, company_id: str, branch_id: str, bilty_type: str, updated_by: str) -> dict:
    """
    Unset any existing primary for this (company, branch, bilty_type),
    then mark book_id as primary.
    """
    db = get_client()
    # Unset existing primary (if any)
    db.table("bilty_book").update({"is_primary": False, "updated_by": updated_by}).eq("company_id", company_id).eq("branch_id", branch_id).eq("bilty_type", bilty_type).eq("is_primary", True).execute()
    # Set new primary
    res = db.table("bilty_book").update({"is_primary": True, "updated_by": updated_by}).eq("book_id", book_id).eq("company_id", company_id).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bilty book not found")
    logger.info("set_primary_book | book_id=%s company=%s branch=%s type=%s", book_id, company_id, branch_id, bilty_type)
    return res.data[0]


# ══════════════════════════════════════════════════════════════
# BILTY RATE
# ══════════════════════════════════════════════════════════════

def create_rate(data: dict) -> dict:
    logger.info("create_rate | company=%s party_type=%s", data.get("company_id"), data.get("party_type"))
    db = get_client()
    res = db.table("bilty_rate").insert(data).execute()
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create bilty rate")
    logger.info("create_rate ok | id=%s", res.data[0].get("rate_id"))
    return res.data[0]


def list_rates(
    company_id: str,
    branch_id: str,
    party_type: str | None = None,
    consignor_id: str | None = None,
    consignee_id: str | None = None,
    destination_city_id: str | None = None,
    is_active: bool = True,
) -> list:
    db = get_client()
    q = (
        db.table("bilty_rate")
        .select("*")
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("is_active", is_active)
        .order("created_at", desc=True)
    )
    if party_type:
        q = q.eq("party_type", party_type)
    if consignor_id:
        q = q.eq("consignor_id", consignor_id)
    if consignee_id:
        q = q.eq("consignee_id", consignee_id)
    if destination_city_id:
        q = q.eq("destination_city_id", destination_city_id)
    return q.execute().data or []


def get_rate(rate_id: str, company_id: str) -> dict | None:
    db = get_client()
    res = (
        db.table("bilty_rate")
        .select("*")
        .eq("rate_id", rate_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def update_rate(rate_id: str, company_id: str, data: dict) -> dict:
    db = get_client()
    res = (
        db.table("bilty_rate")
        .update(data)
        .eq("rate_id", rate_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bilty rate not found")
    return res.data[0]


def delete_rate(rate_id: str, company_id: str, updated_by: str) -> dict:
    """Soft-delete: set is_active=False."""
    return update_rate(
        rate_id,
        company_id,
        {"is_active": False, "updated_by": updated_by},
    )


# ══════════════════════════════════════════════════════════════
# BILTY TEMPLATE
# ══════════════════════════════════════════════════════════════

def create_template(data: dict) -> dict:
    logger.info("create_template | company=%s branch=%s code=%s", data.get("company_id"), data.get("branch_id"), data.get("code"))
    db = get_client()
    res = db.table("bilty_template").insert(data).execute()
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create bilty template")
    logger.info("create_template ok | id=%s", res.data[0].get("template_id"))
    return res.data[0]


def list_templates(
    company_id: str,
    branch_id: str,
    is_active: bool = True,
    template_type: str | None = None,
    book_id: str | None = None,
) -> list:
    db = get_client()
    q = (
        db.table("bilty_template")
        .select("*")
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("is_active", is_active)
        .order("created_at", desc=True)
    )
    if template_type:
        q = q.eq("template_type", template_type)
    if book_id:
        q = q.eq("book_id", book_id)
    return q.execute().data or []


def get_template(template_id: str, company_id: str) -> dict | None:
    db = get_client()
    res = (
        db.table("bilty_template")
        .select("*")
        .eq("template_id", template_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def update_template(template_id: str, company_id: str, data: dict) -> dict:
    db = get_client()
    res = (
        db.table("bilty_template")
        .update(data)
        .eq("template_id", template_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bilty template not found")
    return res.data[0]


def delete_template(template_id: str, company_id: str, updated_by: str) -> dict:
    """Soft-delete: set is_active=False."""
    return update_template(
        template_id,
        company_id,
        {"is_active": False, "updated_by": updated_by},
    )


def get_primary_template(company_id: str, branch_id: str) -> dict | None:
    """Return the primary active template for a branch, or None."""
    db = get_client()
    res = (
        db.table("bilty_template")
        .select("*")
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("is_primary", True)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def set_primary_template(template_id: str, company_id: str, branch_id: str, updated_by: str) -> dict:
    """
    Unset any existing primary template for this (company, branch),
    then mark template_id as primary.
    """
    db = get_client()
    # Unset existing primary (if any)
    db.table("bilty_template").update({"is_primary": False, "updated_by": updated_by}).eq("company_id", company_id).eq("branch_id", branch_id).eq("is_primary", True).execute()
    # Set new primary
    res = db.table("bilty_template").update({"is_primary": True, "updated_by": updated_by}).eq("template_id", template_id).eq("company_id", company_id).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bilty template not found")
    logger.info("set_primary_template | template_id=%s company=%s branch=%s", template_id, company_id, branch_id)
    return res.data[0]


# ══════════════════════════════════════════════════════════════
# BILTY DISCOUNT
# ══════════════════════════════════════════════════════════════

def create_discount(data: dict) -> dict:
    logger.info("create_discount | company=%s branch=%s code=%s", data.get("company_id"), data.get("branch_id"), data.get("discount_code"))
    db = get_client()
    res = db.table("bilty_discount").insert(data).execute()
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create discount")
    logger.info("create_discount ok | id=%s", res.data[0].get("discount_id"))
    return res.data[0]


def list_discounts(
    company_id: str,
    branch_id: str,
    bill_book_id: str | None = None,
    is_active: bool = True,
) -> list:
    db = get_client()
    q = (
        db.table("bilty_discount")
        .select("*")
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("is_active", is_active)
        .order("created_at", desc=True)
    )
    if bill_book_id:
        q = q.eq("bill_book_id", bill_book_id)
    return q.execute().data or []


def get_discount(discount_id: str, company_id: str) -> dict | None:
    db = get_client()
    res = (
        db.table("bilty_discount")
        .select("*")
        .eq("discount_id", discount_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def update_discount(discount_id: str, company_id: str, data: dict) -> dict:
    db = get_client()
    res = (
        db.table("bilty_discount")
        .update(data)
        .eq("discount_id", discount_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Discount not found")
    return res.data[0]


def delete_discount(discount_id: str, company_id: str, updated_by: str) -> dict:
    """Soft-delete: set is_active=False."""
    return update_discount(
        discount_id,
        company_id,
        {"is_active": False, "updated_by": updated_by},
    )
