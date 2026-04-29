import logging
from typing import Optional
from fastapi import HTTPException

from app.services.utils.supabase import get_client

logger = logging.getLogger("movesure.fleet")


# ──────────────────────────────────────────────────────────────────────────────
# Fleet Staff
# ──────────────────────────────────────────────────────────────────────────────

def create_fleet_staff(data: dict) -> dict:
    """Create a new fleet staff record."""
    db = get_client()
    try:
        result = db.table("fleet_staff").insert(data).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create fleet staff")
        logger.info("fleet_staff created: %s", result.data[0]["staff_id"])
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("create_fleet_staff error: %s", e)
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Fleet staff with this license/aadhar already exists")
        raise HTTPException(status_code=500, detail=str(e))


def list_fleet_staff(
    company_id: str,
    branch_id: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = True,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list:
    """List fleet staff with optional filters."""
    db = get_client()
    q = db.table("fleet_staff").select("*").eq("company_id", company_id)
    if branch_id:
        q = q.eq("branch_id", branch_id)
    if role:
        q = q.eq("role", role)
    if is_active is not None:
        q = q.eq("is_active", is_active)
    if search:
        q = q.ilike("name", f"%{search}%")
    result = q.order("name").range(offset, offset + limit - 1).execute()
    return result.data or []


def get_fleet_staff(staff_id: str, company_id: str) -> dict:
    """Get a single fleet staff by ID, scoped to company."""
    db = get_client()
    result = db.table("fleet_staff").select("*").eq("staff_id", staff_id).eq("company_id", company_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Fleet staff not found")
    return result.data[0]


def update_fleet_staff(staff_id: str, company_id: str, data: dict) -> dict:
    """Update a fleet staff record."""
    get_fleet_staff(staff_id, company_id)  # 404 guard
    db = get_client()
    try:
        result = db.table("fleet_staff").update(data).eq("staff_id", staff_id).eq("company_id", company_id).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Update failed")
        logger.info("fleet_staff updated: %s", staff_id)
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("update_fleet_staff error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def delete_fleet_staff(staff_id: str, company_id: str, updated_by: Optional[str] = None) -> dict:
    """Soft-delete a fleet staff record (sets is_active = False)."""
    get_fleet_staff(staff_id, company_id)  # 404 guard
    db = get_client()
    payload: dict = {"is_active": False}
    if updated_by:
        payload["updated_by"] = updated_by
    result = db.table("fleet_staff").update(payload).eq("staff_id", staff_id).eq("company_id", company_id).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Delete failed")
    logger.info("fleet_staff deactivated: %s", staff_id)
    return {"message": "Fleet staff deactivated", "staff_id": staff_id}


# ──────────────────────────────────────────────────────────────────────────────
# Fleet (Vehicles)
# ──────────────────────────────────────────────────────────────────────────────

def create_fleet(data: dict) -> dict:
    """Create a new fleet vehicle record."""
    db = get_client()
    try:
        result = db.table("fleet").insert(data).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create fleet")
        logger.info("fleet created: %s  vehicle_no=%s", result.data[0]["fleet_id"], result.data[0].get("vehicle_no"))
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("create_fleet error: %s", e)
        if "uq_fleet_vehicle_no" in str(e) or "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Vehicle number already registered for this company")
        raise HTTPException(status_code=500, detail=str(e))


def list_fleet(
    company_id: str,
    branch_id: Optional[str] = None,
    vehicle_type: Optional[str] = None,
    status: Optional[str] = None,
    is_active: Optional[bool] = True,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list:
    """
    List fleet vehicles.
    Includes joined staff names for current_driver, current_owner, current_conductor
    via a select that joins fleet_staff.
    """
    db = get_client()
    select_cols = (
        "*,"
        "current_owner:fleet_staff!fleet_current_owner_id_fkey(staff_id,name,mobile,role),"
        "current_driver:fleet_staff!fleet_current_driver_id_fkey(staff_id,name,mobile,role),"
        "current_conductor:fleet_staff!fleet_current_conductor_id_fkey(staff_id,name,mobile,role)"
    )
    q = db.table("fleet").select(select_cols).eq("company_id", company_id)
    if branch_id:
        q = q.eq("branch_id", branch_id)
    if vehicle_type:
        q = q.eq("vehicle_type", vehicle_type)
    if status:
        q = q.eq("status", status)
    if is_active is not None:
        q = q.eq("is_active", is_active)
    if search:
        q = q.ilike("vehicle_no", f"%{search}%")
    result = q.order("vehicle_no").range(offset, offset + limit - 1).execute()
    return result.data or []


def get_fleet(fleet_id: str, company_id: str) -> dict:
    """Get a single fleet vehicle with staff details."""
    db = get_client()
    select_cols = (
        "*,"
        "current_owner:fleet_staff!fleet_current_owner_id_fkey(staff_id,name,mobile,role,license_no,license_expiry),"
        "current_driver:fleet_staff!fleet_current_driver_id_fkey(staff_id,name,mobile,role,license_no,license_expiry),"
        "current_conductor:fleet_staff!fleet_current_conductor_id_fkey(staff_id,name,mobile,role)"
    )
    result = db.table("fleet").select(select_cols).eq("fleet_id", fleet_id).eq("company_id", company_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Fleet vehicle not found")
    return result.data[0]


def update_fleet(fleet_id: str, company_id: str, data: dict) -> dict:
    """Update a fleet vehicle record."""
    db = get_client()
    # Check exists
    existing = db.table("fleet").select("fleet_id").eq("fleet_id", fleet_id).eq("company_id", company_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Fleet vehicle not found")
    try:
        result = db.table("fleet").update(data).eq("fleet_id", fleet_id).eq("company_id", company_id).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Update failed")
        logger.info("fleet updated: %s", fleet_id)
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("update_fleet error: %s", e)
        if "uq_fleet_vehicle_no" in str(e) or "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Vehicle number already registered for this company")
        raise HTTPException(status_code=500, detail=str(e))


def delete_fleet(fleet_id: str, company_id: str, updated_by: Optional[str] = None) -> dict:
    """Soft-delete a fleet vehicle (sets is_active = False, status = INACTIVE)."""
    db = get_client()
    existing = db.table("fleet").select("fleet_id").eq("fleet_id", fleet_id).eq("company_id", company_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Fleet vehicle not found")
    payload: dict = {"is_active": False, "status": "INACTIVE"}
    if updated_by:
        payload["updated_by"] = updated_by
    result = db.table("fleet").update(payload).eq("fleet_id", fleet_id).eq("company_id", company_id).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Delete failed")
    logger.info("fleet deactivated: %s", fleet_id)
    return {"message": "Fleet vehicle deactivated", "fleet_id": fleet_id}


def assign_fleet_staff(
    fleet_id: str,
    company_id: str,
    updated_by: Optional[str],
    owner_id: Optional[str] = None,
    driver_id: Optional[str] = None,
    conductor_id: Optional[str] = None,
) -> dict:
    """
    Assign owner / driver / conductor to a fleet vehicle.
    Only supplied fields are updated — passing None leaves the existing
    assignment untouched.  Pass the empty string "" to explicitly clear.
    """
    db = get_client()
    existing = db.table("fleet").select("fleet_id").eq("fleet_id", fleet_id).eq("company_id", company_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Fleet vehicle not found")

    payload: dict = {}
    if owner_id is not None:
        payload["current_owner_id"] = owner_id or None
    if driver_id is not None:
        payload["current_driver_id"] = driver_id or None
    if conductor_id is not None:
        payload["current_conductor_id"] = conductor_id or None
    if updated_by:
        payload["updated_by"] = updated_by

    if not payload or payload == {"updated_by": updated_by}:
        raise HTTPException(status_code=400, detail="Provide at least one of: owner_id, driver_id, conductor_id")

    # Validate that the provided staff IDs belong to this company
    for field, sid in [("owner_id", owner_id), ("driver_id", driver_id), ("conductor_id", conductor_id)]:
        if sid:
            check = db.table("fleet_staff").select("staff_id").eq("staff_id", sid).eq("company_id", company_id).execute()
            if not check.data:
                raise HTTPException(status_code=404, detail=f"Fleet staff not found for {field}: {sid}")

    result = db.table("fleet").update(payload).eq("fleet_id", fleet_id).eq("company_id", company_id).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Assignment failed")
    logger.info("fleet staff assigned: fleet=%s  payload=%s", fleet_id, payload)
    return result.data[0]
