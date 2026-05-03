import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.services.utils.supabase import get_client

logger = logging.getLogger("movesure.challan")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════
# HELPERS — aggregate recalculation
# ══════════════════════════════════════════════════════════════

def _recalc_challan_totals(challan_id: str, company_id: str, updated_by: str) -> None:
    """Recompute totals on challan from its active bilties."""
    db = get_client()
    rows = (
        db.table("bilty")
        .select("total_amount,weight,no_of_pkg")
        .eq("challan_id", challan_id)
        .eq("company_id", company_id)
        .eq("is_active", True)
        .execute()
        .data or []
    )
    db.table("challan").update({
        "total_bilty_count": len(rows),
        "total_freight":     sum(float(r.get("total_amount") or 0) for r in rows),
        "total_weight":      sum(float(r.get("weight") or 0) for r in rows),
        "total_packages":    sum(int(r.get("no_of_pkg") or 0) for r in rows),
        "updated_by":        updated_by,
    }).eq("challan_id", challan_id).execute()


def _recalc_trip_sheet_totals(trip_sheet_id: str, company_id: str, updated_by: str) -> None:
    """Recompute totals on trip_sheet from its active challans."""
    db = get_client()
    rows = (
        db.table("challan")
        .select("total_bilty_count,total_freight,total_weight,total_packages")
        .eq("trip_sheet_id", trip_sheet_id)
        .eq("company_id", company_id)
        .eq("is_active", True)
        .execute()
        .data or []
    )
    db.table("challan_trip_sheet").update({
        "total_challan_count": len(rows),
        "total_bilty_count":   sum(int(r.get("total_bilty_count") or 0) for r in rows),
        "total_freight":       sum(float(r.get("total_freight") or 0) for r in rows),
        "total_weight":        sum(float(r.get("total_weight") or 0) for r in rows),
        "total_packages":      sum(int(r.get("total_packages") or 0) for r in rows),
        "updated_by":          updated_by,
    }).eq("trip_sheet_id", trip_sheet_id).execute()


# ══════════════════════════════════════════════════════════════
# CHALLAN TEMPLATE
# ══════════════════════════════════════════════════════════════

def create_challan_template(data: dict) -> dict:
    logger.info("create_challan_template | company=%s branch=%s type=%s",
                data.get("company_id"), data.get("branch_id"), data.get("template_type"))
    db = get_client()
    res = db.table("challan_template").insert(data).execute()
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create challan template")
    logger.info("create_challan_template ok | id=%s", res.data[0].get("template_id"))
    return res.data[0]


def list_challan_templates(
    company_id: str,
    branch_id: str,
    template_type: str | None = None,
    is_active: bool = True,
) -> list:
    db = get_client()
    q = (
        db.table("challan_template")
        .select("*")
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("is_active", is_active)
        .order("created_at", desc=True)
    )
    if template_type:
        q = q.eq("template_type", template_type)
    return q.execute().data or []


def get_challan_template(template_id: str, company_id: str) -> dict | None:
    db = get_client()
    res = (
        db.table("challan_template")
        .select("*")
        .eq("template_id", template_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def update_challan_template(template_id: str, company_id: str, data: dict) -> dict:
    db = get_client()
    res = (
        db.table("challan_template")
        .update(data)
        .eq("template_id", template_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challan template not found")
    return res.data[0]


def delete_challan_template(template_id: str, company_id: str, updated_by: str) -> dict:
    return update_challan_template(
        template_id, company_id,
        {"is_active": False, "is_default": False, "updated_by": updated_by},
    )


def get_primary_challan_template(
    company_id: str, branch_id: str, template_type: str = "CHALLAN"
) -> dict | None:
    db = get_client()
    res = (
        db.table("challan_template")
        .select("*")
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("template_type", template_type)
        .eq("is_default", True)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def set_primary_challan_template(
    template_id: str, company_id: str, branch_id: str,
    template_type: str, updated_by: str,
) -> dict:
    db = get_client()
    # Clear existing default for this type
    db.table("challan_template").update(
        {"is_default": False, "updated_by": updated_by}
    ).eq("company_id", company_id).eq("branch_id", branch_id).eq(
        "template_type", template_type
    ).eq("is_default", True).execute()
    # Set new default
    res = db.table("challan_template").update(
        {"is_default": True, "updated_by": updated_by}
    ).eq("template_id", template_id).eq("company_id", company_id).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challan template not found")
    logger.info("set_primary_challan_template | id=%s company=%s type=%s",
                template_id, company_id, template_type)
    return res.data[0]


# ══════════════════════════════════════════════════════════════
# CHALLAN BOOK
# ══════════════════════════════════════════════════════════════

def next_challan_no(book_id: str) -> dict:
    """Atomically claims the next challan number from a challan_book row."""
    logger.info("next_challan_no | book_id=%s", book_id)
    db = get_client()
    try:
        res = db.rpc("fn_next_challan_no", {"p_book_id": book_id}).execute()
    except Exception as exc:
        msg = str(exc)
        logger.warning("next_challan_no failed | book_id=%s | %s", book_id, msg)
        if "exhausted" in msg or "completed" in msg:
            raise HTTPException(status.HTTP_410_GONE, "Challan book exhausted — all numbers used")
        if "not available" in msg:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Challan book not found or inactive")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Challan number generation returned no data")
    result = res.data[0]
    logger.info("next_challan_no ok | challan_no=%s", result.get("challan_no"))
    return result


def create_challan_book(data: dict) -> dict:
    logger.info("create_challan_book | company=%s branch=%s",
                data.get("company_id"), data.get("branch_id"))
    if "current_number" not in data and "from_number" in data:
        data["current_number"] = data["from_number"]
    db = get_client()
    res = db.table("challan_book").insert(data).execute()
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create challan book")
    logger.info("create_challan_book ok | id=%s", res.data[0].get("book_id"))
    return res.data[0]


def list_challan_books(
    company_id: str,
    branch_id: str,
    route_scope: str | None = None,
    from_branch_id: str | None = None,
    to_branch_id: str | None = None,
    is_active: bool = True,
    is_completed: bool | None = None,
    is_primary: bool | None = None,
) -> list:
    db = get_client()
    q = (
        db.table("challan_book")
        .select("*")
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("is_active", is_active)
        .order("created_at", desc=True)
    )
    if route_scope:
        q = q.eq("route_scope", route_scope)
    if from_branch_id:
        q = q.eq("from_branch_id", from_branch_id)
    if to_branch_id:
        q = q.eq("to_branch_id", to_branch_id)
    if is_completed is not None:
        q = q.eq("is_completed", is_completed)
    if is_primary is not None:
        q = q.eq("is_primary", is_primary)
    return q.execute().data or []


def get_challan_book(book_id: str, company_id: str) -> dict | None:
    db = get_client()
    res = (
        db.table("challan_book")
        .select("*")
        .eq("book_id", book_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def update_challan_book(book_id: str, company_id: str, data: dict) -> dict:
    db = get_client()
    res = (
        db.table("challan_book")
        .update(data)
        .eq("book_id", book_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challan book not found")
    return res.data[0]


def delete_challan_book(book_id: str, company_id: str, updated_by: str) -> dict:
    return update_challan_book(
        book_id, company_id,
        {"is_active": False, "is_primary": False, "updated_by": updated_by},
    )


def get_primary_challan_book(company_id: str, branch_id: str) -> dict | None:
    db = get_client()
    res = (
        db.table("challan_book")
        .select("*")
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("is_primary", True)
        .eq("is_active", True)
        .eq("is_completed", False)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def set_primary_challan_book(
    book_id: str, company_id: str, branch_id: str, updated_by: str
) -> dict:
    db = get_client()
    # Unset existing primary
    db.table("challan_book").update(
        {"is_primary": False, "updated_by": updated_by}
    ).eq("company_id", company_id).eq("branch_id", branch_id).eq("is_primary", True).execute()
    # Set new primary
    res = db.table("challan_book").update(
        {"is_primary": True, "updated_by": updated_by}
    ).eq("book_id", book_id).eq("company_id", company_id).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challan book not found")
    logger.info("set_primary_challan_book | id=%s company=%s branch=%s",
                book_id, company_id, branch_id)
    return res.data[0]


def get_book_for_route(
    company_id: str,
    from_branch_id: str,
    to_branch_id: str,
) -> dict | None:
    """Return the active, non-exhausted FIXED_ROUTE book for a specific from→to leg."""
    db = get_client()
    res = (
        db.table("challan_book")
        .select("*")
        .eq("company_id", company_id)
        .eq("route_scope", "FIXED_ROUTE")
        .eq("from_branch_id", from_branch_id)
        .eq("to_branch_id", to_branch_id)
        .eq("is_active", True)
        .eq("is_completed", False)
        .order("is_primary", desc=True)   # primary book first if multiple exist
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


# ══════════════════════════════════════════════════════════════
# CHALLAN TRIP SHEET
# ══════════════════════════════════════════════════════════════

def create_trip_sheet(data: dict) -> dict:
    logger.info("create_trip_sheet | company=%s no=%s",
                data.get("company_id"), data.get("trip_sheet_no"))
    db = get_client()
    res = db.table("challan_trip_sheet").insert(data).execute()
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create trip sheet")
    logger.info("create_trip_sheet ok | id=%s", res.data[0].get("trip_sheet_id"))
    return res.data[0]


def list_trip_sheets(
    company_id: str,
    trip_status: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    is_active: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> list:
    db = get_client()
    q = (
        db.table("challan_trip_sheet")
        .select("*")
        .eq("company_id", company_id)
        .eq("is_active", is_active)
        .order("trip_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .offset(offset)
    )
    if trip_status:
        q = q.eq("status", trip_status)
    if from_date:
        q = q.gte("trip_date", from_date)
    if to_date:
        q = q.lte("trip_date", to_date)
    return q.execute().data or []


def get_trip_sheet(trip_sheet_id: str, company_id: str) -> dict | None:
    db = get_client()
    res = (
        db.table("challan_trip_sheet")
        .select("*")
        .eq("trip_sheet_id", trip_sheet_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def get_trip_sheet_with_challans(trip_sheet_id: str, company_id: str) -> dict | None:
    """Return the trip sheet + all its challans."""
    sheet = get_trip_sheet(trip_sheet_id, company_id)
    if not sheet:
        return None
    db = get_client()
    challans = (
        db.table("challan")
        .select("*")
        .eq("trip_sheet_id", trip_sheet_id)
        .eq("company_id", company_id)
        .eq("is_active", True)
        .order("created_at", desc=True)
        .execute()
        .data or []
    )
    sheet["challans"] = challans
    return sheet


def list_trip_sheet_challans(
    trip_sheet_id: str,
    company_id: str,
    viewing_branch_id: str | None = None,
) -> list:
    """
    Return all challans attached to a trip sheet, across all branches.
    Each challan gets an `is_mine` boolean flag so the frontend can
    visually separate the current branch's challan from others.
    Also attaches a lightweight `bilties` list to each challan.
    """
    db = get_client()
    challans = (
        db.table("challan")
        .select("*")
        .eq("trip_sheet_id", trip_sheet_id)
        .eq("company_id", company_id)
        .eq("is_active", True)
        .order("branch_id")
        .order("created_at")
        .execute()
        .data or []
    )
    for ch in challans:
        ch["is_mine"] = (viewing_branch_id is not None
                         and ch.get("branch_id") == viewing_branch_id)
        bilties = (
            db.table("bilty")
            .select(
                "bilty_id,gr_no,bilty_date,"
                "consignor_name,consignee_name,"
                "from_city_id,to_city_id,"
                "no_of_pkg,weight,total_amount,"
                "delivery_type,payment_mode,status"
            )
            .eq("challan_id", ch["challan_id"])
            .eq("company_id", company_id)
            .eq("is_active", True)
            .order("created_at")
            .execute()
            .data or []
        )
        ch["bilties"] = bilties
    return challans


def update_trip_sheet(trip_sheet_id: str, company_id: str, data: dict) -> dict:
    db = get_client()
    res = (
        db.table("challan_trip_sheet")
        .update(data)
        .eq("trip_sheet_id", trip_sheet_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip sheet not found")
    return res.data[0]


def dispatch_trip_sheet(trip_sheet_id: str, company_id: str, user_id: str) -> dict:
    sheet = get_trip_sheet(trip_sheet_id, company_id)
    if not sheet:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip sheet not found")
    if sheet["status"] in ("DISPATCHED", "ARRIVED", "CLOSED"):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Trip sheet is already {sheet['status']}")
    now = _now()
    return update_trip_sheet(trip_sheet_id, company_id, {
        "status":        "DISPATCHED",
        "is_dispatched": True,
        "dispatched_at": now,
        "dispatched_by": user_id,
        "updated_by":    user_id,
    })


def arrive_trip_sheet(trip_sheet_id: str, company_id: str, user_id: str) -> dict:
    sheet = get_trip_sheet(trip_sheet_id, company_id)
    if not sheet:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip sheet not found")
    if sheet["status"] != "DISPATCHED":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Trip sheet must be DISPATCHED before it can ARRIVE")
    now = _now()
    return update_trip_sheet(trip_sheet_id, company_id, {
        "status":     "ARRIVED",
        "is_arrived": True,
        "arrived_at": now,
        "arrived_by": user_id,
        "updated_by": user_id,
    })


# ══════════════════════════════════════════════════════════════
# CHALLAN
# ══════════════════════════════════════════════════════════════

def create_challan(data: dict) -> dict:
    logger.info("create_challan | company=%s branch=%s no=%s",
                data.get("company_id"), data.get("branch_id"), data.get("challan_no"))
    db = get_client()
    res = db.table("challan").insert(data).execute()
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create challan")
    logger.info("create_challan ok | id=%s", res.data[0].get("challan_id"))
    return res.data[0]


def list_challans(
    company_id: str,
    branch_id: str | None = None,
    challan_status: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    trip_sheet_id: str | None = None,
    is_active: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> list:
    db = get_client()
    q = (
        db.table("challan")
        .select("*")
        .eq("company_id", company_id)
        .eq("is_active", is_active)
        .order("challan_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .offset(offset)
    )
    if branch_id:
        q = q.eq("branch_id", branch_id)
    if challan_status:
        q = q.eq("status", challan_status)
    if from_date:
        q = q.gte("challan_date", from_date)
    if to_date:
        q = q.lte("challan_date", to_date)
    if trip_sheet_id:
        q = q.eq("trip_sheet_id", trip_sheet_id)
    return q.execute().data or []


def get_challan(challan_id: str, company_id: str) -> dict | None:
    db = get_client()
    res = (
        db.table("challan")
        .select("*")
        .eq("challan_id", challan_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def get_challan_with_bilties(challan_id: str, company_id: str) -> dict | None:
    """Return the challan + its active bilties."""
    challan = get_challan(challan_id, company_id)
    if not challan:
        return None
    db = get_client()
    bilties = (
        db.table("bilty")
        .select(
            "bilty_id,gr_no,bilty_date,bilty_type,"
            "consignor_name,consignor_mobile,"
            "consignee_name,consignee_mobile,"
            "from_city_id,to_city_id,"
            "delivery_type,payment_mode,"
            "contain,pvt_marks,"
            "no_of_pkg,weight,actual_weight,total_amount,"
            "invoice_no,invoice_value,"
            "status,challan_assigned_at"
        )
        .eq("challan_id", challan_id)
        .eq("company_id", company_id)
        .eq("is_active", True)
        .order("created_at", desc=True)
        .execute()
        .data or []
    )
    challan["bilties"] = bilties
    return challan


def update_challan(challan_id: str, company_id: str, data: dict) -> dict:
    db = get_client()
    res = (
        db.table("challan")
        .update(data)
        .eq("challan_id", challan_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challan not found")
    return res.data[0]


def get_primary_challan(company_id: str, branch_id: str) -> dict | None:
    db = get_client()
    res = (
        db.table("challan")
        .select("*")
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("is_primary", True)
        .eq("is_active", True)
        .not_.in_("status", ["DISPATCHED", "ARRIVED_HUB", "CLOSED"])
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def set_primary_challan(
    challan_id: str, company_id: str, branch_id: str, updated_by: str
) -> dict:
    challan = get_challan(challan_id, company_id)
    if not challan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challan not found")
    if challan["status"] in ("DISPATCHED", "ARRIVED_HUB", "CLOSED"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot set a {challan['status']} challan as primary",
        )
    db = get_client()
    # Unset existing primary for this branch
    db.table("challan").update(
        {"is_primary": False, "updated_by": updated_by}
    ).eq("company_id", company_id).eq("branch_id", branch_id).eq("is_primary", True).execute()
    # Set new primary
    res = db.table("challan").update(
        {"is_primary": True, "updated_by": updated_by}
    ).eq("challan_id", challan_id).eq("company_id", company_id).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challan not found")
    logger.info("set_primary_challan | id=%s company=%s branch=%s",
                challan_id, company_id, branch_id)
    return res.data[0]


def dispatch_challan(challan_id: str, company_id: str, user_id: str) -> dict:
    challan = get_challan(challan_id, company_id)
    if not challan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challan not found")
    if challan["status"] in ("DISPATCHED", "ARRIVED_HUB", "CLOSED"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Challan is already {challan['status']}"
        )
    now = _now()
    db = get_client()
    # Dispatch all bilties on this challan
    db.table("bilty").update({
        "is_dispatched":        True,
        "dispatched_at":        now,
        "dispatched_by":        user_id,
        "dispatched_challan_no": challan["challan_no"],
        "status":               "DISPATCHED",
        "updated_by":           user_id,
    }).eq("challan_id", challan_id).eq("company_id", company_id).eq("is_active", True).execute()
    # Dispatch the challan (primary flag cleared — dispatched challan can no longer receive bilties)
    result = update_challan(challan_id, company_id, {
        "status":        "DISPATCHED",
        "is_dispatched": True,
        "dispatched_at": now,
        "dispatched_by": user_id,
        "is_primary":    False,
        "updated_by":    user_id,
    })
    logger.info("dispatch_challan ok | id=%s", challan_id)
    return result


def arrive_hub_challan(challan_id: str, company_id: str, user_id: str) -> dict:
    challan = get_challan(challan_id, company_id)
    if not challan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challan not found")
    if challan["status"] != "DISPATCHED":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Challan must be DISPATCHED before it can ARRIVE_HUB",
        )
    now = _now()
    db = get_client()
    # Update bilties to reached hub
    db.table("bilty").update({
        "is_reached_hub": True,
        "reached_hub_at": now,
        "reached_hub_by": user_id,
        "status":         "REACHED_HUB",
        "updated_by":     user_id,
    }).eq("challan_id", challan_id).eq("company_id", company_id).eq("is_active", True).execute()
    result = update_challan(challan_id, company_id, {
        "status":         "ARRIVED_HUB",
        "is_arrived_hub": True,
        "arrived_hub_at": now,
        "arrived_hub_by": user_id,
        "updated_by":     user_id,
    })
    logger.info("arrive_hub_challan ok | id=%s", challan_id)
    return result


def add_bilty_to_challan(
    challan_id: str, bilty_id: str, company_id: str, user_id: str
) -> dict:
    challan = get_challan(challan_id, company_id)
    if not challan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challan not found")
    if challan["status"] in ("DISPATCHED", "ARRIVED_HUB", "CLOSED"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot add bilty to a {challan['status']} challan",
        )
    db = get_client()
    bilty_res = (
        db.table("bilty")
        .select("bilty_id,challan_id,branch_id,gr_no")
        .eq("bilty_id", bilty_id)
        .eq("company_id", company_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not bilty_res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bilty not found")
    bilty = bilty_res.data[0]
    if bilty.get("challan_id"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Bilty is already assigned to a challan — remove it first",
        )
    now = _now()
    db.table("bilty").update({
        "challan_id":            challan_id,
        "challan_branch_id":     challan["branch_id"],
        "trip_sheet_id":         challan.get("trip_sheet_id"),
        "challan_assigned_at":   now,
        "challan_assigned_by":   user_id,
        "dispatched_challan_no": challan["challan_no"],
        "updated_by":            user_id,
    }).eq("bilty_id", bilty_id).execute()
    _recalc_challan_totals(challan_id, company_id, user_id)
    if challan.get("trip_sheet_id"):
        _recalc_trip_sheet_totals(challan["trip_sheet_id"], company_id, user_id)
    logger.info("add_bilty_to_challan | bilty=%s challan=%s", bilty_id, challan_id)
    return get_challan(challan_id, company_id)


def remove_bilty_from_challan(
    challan_id: str, bilty_id: str, company_id: str, user_id: str
) -> dict:
    challan = get_challan(challan_id, company_id)
    if not challan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challan not found")
    if challan["status"] in ("DISPATCHED", "ARRIVED_HUB", "CLOSED"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot remove bilty from a {challan['status']} challan",
        )
    db = get_client()
    bilty_res = (
        db.table("bilty")
        .select("bilty_id,challan_id,gr_no")
        .eq("bilty_id", bilty_id)
        .eq("company_id", company_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not bilty_res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bilty not found")
    if bilty_res.data[0].get("challan_id") != challan_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Bilty is not on this challan")
    db.table("bilty").update({
        "challan_id":            None,
        "challan_branch_id":     None,
        "trip_sheet_id":         None,
        "challan_assigned_at":   None,
        "challan_assigned_by":   None,
        "dispatched_challan_no": None,
        "updated_by":            user_id,
    }).eq("bilty_id", bilty_id).execute()
    _recalc_challan_totals(challan_id, company_id, user_id)
    if challan.get("trip_sheet_id"):
        _recalc_trip_sheet_totals(challan["trip_sheet_id"], company_id, user_id)
    logger.info("remove_bilty_from_challan | bilty=%s challan=%s", bilty_id, challan_id)
    return get_challan(challan_id, company_id)


def move_to_trip_sheet(
    challan_id: str, trip_sheet_id: str, company_id: str, user_id: str
) -> dict:
    challan = get_challan(challan_id, company_id)
    if not challan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challan not found")
    if challan["status"] in ("DISPATCHED", "ARRIVED_HUB", "CLOSED"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot move a {challan['status']} challan to a trip sheet",
        )
    db = get_client()
    sheet_res = (
        db.table("challan_trip_sheet")
        .select("trip_sheet_id,status")
        .eq("trip_sheet_id", trip_sheet_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    if not sheet_res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip sheet not found")
    sheet = sheet_res.data[0]
    if sheet["status"] in ("DISPATCHED", "ARRIVED", "CLOSED"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Trip sheet is already {sheet['status']} — cannot add challans",
        )
    old_trip_sheet_id = challan.get("trip_sheet_id")
    result = update_challan(challan_id, company_id, {
        "trip_sheet_id": trip_sheet_id,
        "updated_by":    user_id,
    })
    # Propagate to all bilties on this challan
    db.table("bilty").update({
        "trip_sheet_id": trip_sheet_id,
        "updated_by":    user_id,
    }).eq("challan_id", challan_id).eq("company_id", company_id).eq("is_active", True).execute()
    _recalc_trip_sheet_totals(trip_sheet_id, company_id, user_id)
    if old_trip_sheet_id and old_trip_sheet_id != trip_sheet_id:
        _recalc_trip_sheet_totals(old_trip_sheet_id, company_id, user_id)
    logger.info("move_to_trip_sheet | challan=%s trip_sheet=%s", challan_id, trip_sheet_id)
    return result


def remove_from_trip_sheet(challan_id: str, company_id: str, user_id: str) -> dict:
    challan = get_challan(challan_id, company_id)
    if not challan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challan not found")
    old_trip_sheet_id = challan.get("trip_sheet_id")
    if not old_trip_sheet_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Challan is not attached to any trip sheet")
    db = get_client()
    result = update_challan(challan_id, company_id, {
        "trip_sheet_id": None,
        "updated_by":    user_id,
    })
    db.table("bilty").update({
        "trip_sheet_id": None,
        "updated_by":    user_id,
    }).eq("challan_id", challan_id).eq("company_id", company_id).eq("is_active", True).execute()
    _recalc_trip_sheet_totals(old_trip_sheet_id, company_id, user_id)
    logger.info("remove_from_trip_sheet | challan=%s trip_sheet=%s", challan_id, old_trip_sheet_id)
    return result


def list_challan_bilties(challan_id: str, company_id: str) -> list:
    db = get_client()
    return (
        db.table("bilty")
        .select("*")
        .eq("challan_id", challan_id)
        .eq("company_id", company_id)
        .eq("is_active", True)
        .order("created_at", desc=True)
        .execute()
        .data or []
    )


def list_available_bilties(
    company_id: str,
    branch_id: str,
    to_city_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list:
    """
    Bilties that are SAVED (not draft) and not yet assigned to any challan.
    These are the bilties eligible for challan assignment.
    """
    db = get_client()
    q = (
        db.table("bilty")
        .select(
            "bilty_id,gr_no,bilty_date,bilty_type,"
            "consignor_name,consignor_mobile,"
            "consignee_name,consignee_mobile,"
            "from_city_id,to_city_id,"
            "delivery_type,payment_mode,"
            "contain,pvt_marks,"
            "no_of_pkg,weight,actual_weight,total_amount,"
            "invoice_no,invoice_value,"
            "status"
        )
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("is_active", True)
        .is_("challan_id", "null")
        .eq("status", "SAVED")
        .order("bilty_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .offset(offset)
    )
    if to_city_id:
        q = q.eq("to_city_id", to_city_id)
    if from_date:
        q = q.gte("bilty_date", from_date)
    if to_date:
        q = q.lte("bilty_date", to_date)
    return q.execute().data or []


def list_draft_bilties(
    company_id: str,
    branch_id: str,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list:
    """Return DRAFT bilties for the branch (not yet saved/confirmed)."""
    db = get_client()
    q = (
        db.table("bilty")
        .select(
            "bilty_id,gr_no,bilty_date,bilty_type,"
            "consignor_name,consignor_mobile,"
            "consignee_name,consignee_mobile,"
            "from_city_id,to_city_id,"
            "delivery_type,payment_mode,"
            "contain,pvt_marks,"
            "no_of_pkg,weight,actual_weight,total_amount,"
            "invoice_no,invoice_value,"
            "status,created_at"
        )
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("is_active", True)
        .eq("status", "DRAFT")
        .order("created_at", desc=True)
        .limit(limit)
        .offset(offset)
    )
    if from_date:
        q = q.gte("bilty_date", from_date)
    if to_date:
        q = q.lte("bilty_date", to_date)
    return q.execute().data or []
