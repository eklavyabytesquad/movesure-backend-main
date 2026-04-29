import logging
from fastapi import HTTPException, status
from app.services.utils.supabase import get_client

logger = logging.getLogger("movesure.master")

# ── Helpers ────────────────────────────────────────────────────────────────────

def _raise_not_found(entity: str, id_: str):
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"{entity} '{id_}' not found in your company.")

def _raise_conflict(msg: str):
    raise HTTPException(status.HTTP_409_CONFLICT, msg)

def _raise_500(msg: str):
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, msg)


# ══════════════════════════════════════════════════════════════════════════════
# MASTER STATE
# ══════════════════════════════════════════════════════════════════════════════

def create_state(company_id: str, branch_id: str, data: dict, created_by: str | None = None) -> dict:
    db = get_client()
    # duplicate check
    dup = (
        db.table("master_state")
        .select("state_id")
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("state_code", data["state_code"])
        .limit(1)
        .execute()
    )
    if dup.data:
        _raise_conflict(f"State with code '{data['state_code']}' already exists in this branch.")

    row = {
        **data,
        "company_id": company_id,
        "branch_id":  branch_id,
    }
    if created_by:
        row["created_by"] = created_by
        row["updated_by"] = created_by

    res = db.table("master_state").insert(row).execute()
    if not res.data:
        _raise_500("Failed to create state.")
    return res.data[0]


def bulk_create_states(company_id: str, branch_id: str, items: list[dict], created_by: str | None = None) -> dict:
    """Insert multiple states; returns created rows and any per-item errors."""
    db = get_client()
    rows, errors = [], []

    for i, item in enumerate(items):
        dup = (
            db.table("master_state")
            .select("state_id")
            .eq("company_id", company_id)
            .eq("branch_id", branch_id)
            .eq("state_code", item.get("state_code", ""))
            .limit(1)
            .execute()
        )
        if dup.data:
            errors.append({"index": i, "state_code": item.get("state_code"), "error": "Duplicate state_code in this branch."})
            continue
        row = {**item, "company_id": company_id, "branch_id": branch_id}
        if created_by:
            row["created_by"] = created_by
            row["updated_by"] = created_by
        rows.append(row)

    created = []
    if rows:
        res = db.table("master_state").insert(rows).execute()
        created = res.data or []

    return {"created_count": len(created), "error_count": len(errors), "created": created, "errors": errors}


def list_states(company_id: str, branch_id: str | None = None, is_active: bool | None = None) -> list[dict]:
    db = get_client()
    q = (
        db.table("master_state")
        .select("state_id,state_name,state_code,branch_id,total_city_count,is_active,created_at,updated_at")
        .eq("company_id", company_id)
        .order("state_name")
    )
    if branch_id:
        q = q.eq("branch_id", branch_id)
    if is_active is not None:
        q = q.eq("is_active", is_active)
    return q.execute().data or []


def get_state(state_id: str, company_id: str) -> dict | None:
    db = get_client()
    res = (
        db.table("master_state")
        .select("*")
        .eq("state_id", state_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def update_state(state_id: str, company_id: str, data: dict, updated_by: str | None = None) -> dict:
    db = get_client()
    if updated_by:
        data["updated_by"] = updated_by
    res = (
        db.table("master_state")
        .update(data)
        .eq("state_id", state_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        _raise_not_found("State", state_id)
    return res.data[0]


def bulk_update_states(company_id: str, items: list[dict], updated_by: str | None = None) -> dict:
    """Update multiple states by state_id. Each item must include state_id + fields to update."""
    db = get_client()
    updated, errors = [], []

    for i, item in enumerate(items):
        state_id = item.pop("state_id", None)
        if not state_id:
            errors.append({"index": i, "error": "Missing state_id."})
            continue
        if updated_by:
            item["updated_by"] = updated_by
        res = (
            db.table("master_state")
            .update(item)
            .eq("state_id", state_id)
            .eq("company_id", company_id)
            .execute()
        )
        if res.data:
            updated.append(res.data[0])
        else:
            errors.append({"index": i, "state_id": state_id, "error": "Not found or no change."})

    return {"updated_count": len(updated), "error_count": len(errors), "updated": updated, "errors": errors}


# ══════════════════════════════════════════════════════════════════════════════
# MASTER CITY
# ══════════════════════════════════════════════════════════════════════════════

def _verify_state_ownership(state_id: str, company_id: str):
    """Raise 404 if the state doesn't belong to the company."""
    db = get_client()
    res = db.table("master_state").select("state_id").eq("state_id", state_id).eq("company_id", company_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"State '{state_id}' not found in your company.")


def create_city(company_id: str, branch_id: str, data: dict, created_by: str | None = None) -> dict:
    db = get_client()
    _verify_state_ownership(data["state_id"], company_id)

    dup = (
        db.table("master_city")
        .select("city_id")
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("city_code", data["city_code"])
        .limit(1)
        .execute()
    )
    if dup.data:
        _raise_conflict(f"City with code '{data['city_code']}' already exists in this branch.")

    row = {**data, "company_id": company_id, "branch_id": branch_id}
    if created_by:
        row["created_by"] = created_by
        row["updated_by"] = created_by

    res = db.table("master_city").insert(row).execute()
    if not res.data:
        _raise_500("Failed to create city.")
    return res.data[0]


def bulk_create_cities(company_id: str, branch_id: str, items: list[dict], created_by: str | None = None) -> dict:
    db = get_client()
    rows, errors = [], []

    for i, item in enumerate(items):
        # state ownership
        state_check = db.table("master_state").select("state_id").eq("state_id", item.get("state_id", "")).eq("company_id", company_id).limit(1).execute()
        if not state_check.data:
            errors.append({"index": i, "city_code": item.get("city_code"), "error": f"State '{item.get('state_id')}' not found."})
            continue

        dup = (
            db.table("master_city")
            .select("city_id")
            .eq("company_id", company_id)
            .eq("branch_id", branch_id)
            .eq("city_code", item.get("city_code", ""))
            .limit(1)
            .execute()
        )
        if dup.data:
            errors.append({"index": i, "city_code": item.get("city_code"), "error": "Duplicate city_code in this branch."})
            continue

        row = {**item, "company_id": company_id, "branch_id": branch_id}
        if created_by:
            row["created_by"] = created_by
            row["updated_by"] = created_by
        rows.append(row)

    created = []
    if rows:
        res = db.table("master_city").insert(rows).execute()
        created = res.data or []

    return {"created_count": len(created), "error_count": len(errors), "created": created, "errors": errors}


def list_cities(
    company_id: str,
    branch_id: str | None = None,
    state_id: str | None = None,
    is_active: bool | None = None,
) -> list[dict]:
    db = get_client()
    q = (
        db.table("master_city")
        .select("city_id,city_name,city_code,city_pin_code,state_id,branch_id,is_active,created_at,updated_at")
        .eq("company_id", company_id)
        .order("city_name")
    )
    if branch_id:
        q = q.eq("branch_id", branch_id)
    if state_id:
        q = q.eq("state_id", state_id)
    if is_active is not None:
        q = q.eq("is_active", is_active)
    return q.execute().data or []


def get_city(city_id: str, company_id: str) -> dict | None:
    db = get_client()
    res = (
        db.table("master_city")
        .select("*")
        .eq("city_id", city_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def update_city(city_id: str, company_id: str, data: dict, updated_by: str | None = None) -> dict:
    db = get_client()
    if "state_id" in data:
        _verify_state_ownership(data["state_id"], company_id)
    if updated_by:
        data["updated_by"] = updated_by
    res = (
        db.table("master_city")
        .update(data)
        .eq("city_id", city_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        _raise_not_found("City", city_id)
    return res.data[0]


def bulk_update_cities(company_id: str, items: list[dict], updated_by: str | None = None) -> dict:
    db = get_client()
    updated, errors = [], []

    for i, item in enumerate(items):
        city_id = item.pop("city_id", None)
        if not city_id:
            errors.append({"index": i, "error": "Missing city_id."})
            continue
        if "state_id" in item:
            state_check = db.table("master_state").select("state_id").eq("state_id", item["state_id"]).eq("company_id", company_id).limit(1).execute()
            if not state_check.data:
                errors.append({"index": i, "city_id": city_id, "error": f"State '{item['state_id']}' not found."})
                continue
        if updated_by:
            item["updated_by"] = updated_by
        res = (
            db.table("master_city")
            .update(item)
            .eq("city_id", city_id)
            .eq("company_id", company_id)
            .execute()
        )
        if res.data:
            updated.append(res.data[0])
        else:
            errors.append({"index": i, "city_id": city_id, "error": "Not found or no change."})

    return {"updated_count": len(updated), "error_count": len(errors), "updated": updated, "errors": errors}


# ══════════════════════════════════════════════════════════════════════════════
# MASTER TRANSPORT
# ══════════════════════════════════════════════════════════════════════════════

def create_transport(company_id: str, branch_id: str, data: dict, created_by: str | None = None) -> dict:
    db = get_client()
    dup = (
        db.table("master_transport")
        .select("transport_id")
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("transport_code", data["transport_code"])
        .limit(1)
        .execute()
    )
    if dup.data:
        _raise_conflict(f"Transport with code '{data['transport_code']}' already exists in this branch.")

    row = {**data, "company_id": company_id, "branch_id": branch_id}
    if created_by:
        row["created_by"] = created_by
        row["updated_by"] = created_by

    res = db.table("master_transport").insert(row).execute()
    if not res.data:
        _raise_500("Failed to create transport.")
    return res.data[0]


def bulk_create_transports(company_id: str, branch_id: str, items: list[dict], created_by: str | None = None) -> dict:
    db = get_client()
    rows, errors = [], []

    for i, item in enumerate(items):
        dup = (
            db.table("master_transport")
            .select("transport_id")
            .eq("company_id", company_id)
            .eq("branch_id", branch_id)
            .eq("transport_code", item.get("transport_code", ""))
            .limit(1)
            .execute()
        )
        if dup.data:
            errors.append({"index": i, "transport_code": item.get("transport_code"), "error": "Duplicate transport_code in this branch."})
            continue
        row = {**item, "company_id": company_id, "branch_id": branch_id}
        if created_by:
            row["created_by"] = created_by
            row["updated_by"] = created_by
        rows.append(row)

    created = []
    if rows:
        res = db.table("master_transport").insert(rows).execute()
        created = res.data or []

    return {"created_count": len(created), "error_count": len(errors), "created": created, "errors": errors}


def list_transports(
    company_id: str,
    branch_id: str | None = None,
    is_active: bool | None = None,
) -> list[dict]:
    db = get_client()
    q = (
        db.table("master_transport")
        .select("transport_id,transport_code,transport_name,gstin,mobile_number_owner,website,address,branch_id,is_active,created_at,updated_at")
        .eq("company_id", company_id)
        .order("transport_name")
    )
    if branch_id:
        q = q.eq("branch_id", branch_id)
    if is_active is not None:
        q = q.eq("is_active", is_active)
    return q.execute().data or []


def get_transport(transport_id: str, company_id: str) -> dict | None:
    db = get_client()
    res = (
        db.table("master_transport")
        .select("*")
        .eq("transport_id", transport_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def update_transport(transport_id: str, company_id: str, data: dict, updated_by: str | None = None) -> dict:
    db = get_client()
    if updated_by:
        data["updated_by"] = updated_by
    res = (
        db.table("master_transport")
        .update(data)
        .eq("transport_id", transport_id)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        _raise_not_found("Transport", transport_id)
    return res.data[0]


def bulk_update_transports(company_id: str, items: list[dict], updated_by: str | None = None) -> dict:
    db = get_client()
    updated, errors = [], []

    for i, item in enumerate(items):
        transport_id = item.pop("transport_id", None)
        if not transport_id:
            errors.append({"index": i, "error": "Missing transport_id."})
            continue
        if updated_by:
            item["updated_by"] = updated_by
        res = (
            db.table("master_transport")
            .update(item)
            .eq("transport_id", transport_id)
            .eq("company_id", company_id)
            .execute()
        )
        if res.data:
            updated.append(res.data[0])
        else:
            errors.append({"index": i, "transport_id": transport_id, "error": "Not found or no change."})

    return {"updated_count": len(updated), "error_count": len(errors), "updated": updated, "errors": errors}


# ══════════════════════════════════════════════════════════════════════════════
# MASTER CITY-WISE TRANSPORT
# ══════════════════════════════════════════════════════════════════════════════

def _verify_city_ownership(city_id: str, company_id: str):
    db = get_client()
    res = db.table("master_city").select("city_id").eq("city_id", city_id).eq("company_id", company_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"City '{city_id}' not found in your company.")


def _verify_transport_ownership(transport_id: str, company_id: str):
    db = get_client()
    res = db.table("master_transport").select("transport_id").eq("transport_id", transport_id).eq("company_id", company_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Transport '{transport_id}' not found in your company.")


def create_city_transport(company_id: str, branch_id: str, data: dict, created_by: str | None = None) -> dict:
    db = get_client()
    _verify_city_ownership(data["city_id"], company_id)
    _verify_transport_ownership(data["transport_id"], company_id)

    dup = (
        db.table("master_city_wise_transport")
        .select("id")
        .eq("company_id", company_id)
        .eq("branch_id", branch_id)
        .eq("city_id", data["city_id"])
        .eq("transport_id", data["transport_id"])
        .limit(1)
        .execute()
    )
    if dup.data:
        _raise_conflict("This transport is already linked to that city in this branch.")

    row = {**data, "company_id": company_id, "branch_id": branch_id}
    if created_by:
        row["created_by"] = created_by
        row["updated_by"] = created_by

    res = db.table("master_city_wise_transport").insert(row).execute()
    if not res.data:
        _raise_500("Failed to create city-transport link.")
    return res.data[0]


def bulk_create_city_transports(company_id: str, branch_id: str, items: list[dict], created_by: str | None = None) -> dict:
    db = get_client()
    rows, errors = [], []

    for i, item in enumerate(items):
        city_check = db.table("master_city").select("city_id").eq("city_id", item.get("city_id", "")).eq("company_id", company_id).limit(1).execute()
        if not city_check.data:
            errors.append({"index": i, "error": f"City '{item.get('city_id')}' not found."})
            continue
        transport_check = db.table("master_transport").select("transport_id").eq("transport_id", item.get("transport_id", "")).eq("company_id", company_id).limit(1).execute()
        if not transport_check.data:
            errors.append({"index": i, "error": f"Transport '{item.get('transport_id')}' not found."})
            continue
        dup = (
            db.table("master_city_wise_transport")
            .select("id")
            .eq("company_id", company_id)
            .eq("branch_id", branch_id)
            .eq("city_id", item.get("city_id", ""))
            .eq("transport_id", item.get("transport_id", ""))
            .limit(1)
            .execute()
        )
        if dup.data:
            errors.append({"index": i, "error": "Duplicate city+transport link in this branch."})
            continue
        row = {**item, "company_id": company_id, "branch_id": branch_id}
        if created_by:
            row["created_by"] = created_by
            row["updated_by"] = created_by
        rows.append(row)

    created = []
    if rows:
        res = db.table("master_city_wise_transport").insert(rows).execute()
        created = res.data or []

    return {"created_count": len(created), "error_count": len(errors), "created": created, "errors": errors}


def list_city_transports(
    company_id: str,
    branch_id: str | None = None,
    city_id: str | None = None,
    transport_id: str | None = None,
    is_active: bool | None = None,
) -> list[dict]:
    db = get_client()
    q = (
        db.table("master_city_wise_transport")
        .select("id,city_id,transport_id,branch_id,branch_mobile,address,manager_name,is_active,created_at,updated_at")
        .eq("company_id", company_id)
        .order("created_at", desc=True)
    )
    if branch_id:
        q = q.eq("branch_id", branch_id)
    if city_id:
        q = q.eq("city_id", city_id)
    if transport_id:
        q = q.eq("transport_id", transport_id)
    if is_active is not None:
        q = q.eq("is_active", is_active)
    return q.execute().data or []


def get_city_transport(id_: str, company_id: str) -> dict | None:
    db = get_client()
    res = (
        db.table("master_city_wise_transport")
        .select("*")
        .eq("id", id_)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def update_city_transport(id_: str, company_id: str, data: dict, updated_by: str | None = None) -> dict:
    db = get_client()
    if updated_by:
        data["updated_by"] = updated_by
    res = (
        db.table("master_city_wise_transport")
        .update(data)
        .eq("id", id_)
        .eq("company_id", company_id)
        .execute()
    )
    if not res.data:
        _raise_not_found("City-transport link", id_)
    return res.data[0]


def bulk_update_city_transports(company_id: str, items: list[dict], updated_by: str | None = None) -> dict:
    db = get_client()
    updated, errors = [], []

    for i, item in enumerate(items):
        id_ = item.pop("id", None)
        if not id_:
            errors.append({"index": i, "error": "Missing id."})
            continue
        if updated_by:
            item["updated_by"] = updated_by
        res = (
            db.table("master_city_wise_transport")
            .update(item)
            .eq("id", id_)
            .eq("company_id", company_id)
            .execute()
        )
        if res.data:
            updated.append(res.data[0])
        else:
            errors.append({"index": i, "id": id_, "error": "Not found or no change."})

    return {"updated_count": len(updated), "error_count": len(errors), "updated": updated, "errors": errors}
