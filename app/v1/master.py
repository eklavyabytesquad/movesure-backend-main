from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from typing import Any

from app.middleware.auth import get_current_user
from app.services.tenant.service import (
    create_branch,
    list_branches,
    get_branch_by_id,
    update_branch,
)
from app.services.master.service import (
    # state
    create_state, bulk_create_states,
    list_states, get_state, update_state, bulk_update_states,
    # city
    create_city, bulk_create_cities,
    list_cities, get_city, update_city, bulk_update_cities,
    # transport
    create_transport, bulk_create_transports,
    list_transports, get_transport, update_transport, bulk_update_transports,
    # city-transport
    create_city_transport, bulk_create_city_transports,
    list_city_transports, get_city_transport, update_city_transport, bulk_update_city_transports,
)

router = APIRouter(prefix="/master", tags=["Master Data"])


# ══════════════════════════════════════════════════════════════════════════════
# Pydantic models — Branch
# ══════════════════════════════════════════════════════════════════════════════

class BranchCreate(BaseModel):
    name:        str            = Field(..., min_length=2, max_length=255)
    branch_code: str            = Field(..., min_length=1, max_length=50, description="Must be unique within your company")
    branch_type: str            = Field("branch", pattern="^(primary|hub|branch)$")
    address:     str | None     = None
    metadata:    dict[str, Any] = {}


class BranchUpdate(BaseModel):
    name:        str | None            = Field(None, min_length=2, max_length=255)
    branch_code: str | None            = Field(None, min_length=1, max_length=50)
    branch_type: str | None            = Field(None, pattern="^(primary|hub|branch)$")
    address:     str | None            = None
    metadata:    dict[str, Any] | None = None


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — BRANCH
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/branches",
    status_code=201,
    summary="Create a new branch in your company",
)
def api_create_branch(body: BranchCreate, current_user: dict = Depends(get_current_user)):
    company_id = current_user["company_id"]
    data = body.model_dump()
    data["company_id"] = company_id
    data["created_by"] = current_user.get("sub")
    data["updated_by"] = current_user.get("sub")
    result = create_branch(data)
    return {"message": "Branch created.", "branch": result}


@router.get(
    "/branches",
    summary="List all branches in your company",
)
def api_list_branches(current_user: dict = Depends(get_current_user)):
    branches = list_branches(current_user["company_id"])
    return {"count": len(branches), "branches": branches}


@router.get(
    "/branches/{branch_id}",
    summary="Get a single branch",
)
def api_get_branch(branch_id: str, current_user: dict = Depends(get_current_user)):
    branch = get_branch_by_id(branch_id, current_user["company_id"])
    if not branch:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Branch '{branch_id}' not found in your company.")
    return branch


@router.patch(
    "/branches/{branch_id}",
    summary="Update a branch",
)
def api_update_branch(branch_id: str, body: BranchUpdate, current_user: dict = Depends(get_current_user)):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update.")
    data["updated_by"] = current_user.get("sub")
    result = update_branch(branch_id, current_user["company_id"], data)
    return {"message": "Branch updated.", "branch": result}


# ══════════════════════════════════════════════════════════════════════════════
# Pydantic models — State
# ══════════════════════════════════════════════════════════════════════════════

class StateCreate(BaseModel):
    state_name:  str = Field(..., min_length=2, max_length=100)
    state_code:  str = Field(..., min_length=1, max_length=10)
    branch_id:   str = Field(..., description="Branch UUID this state belongs to")
    is_active:   bool = True


class StateUpdate(BaseModel):
    state_name: str | None = Field(None, min_length=2, max_length=100)
    state_code: str | None = Field(None, min_length=1, max_length=10)
    is_active:  bool | None = None


class StateBulkUpdateItem(StateUpdate):
    state_id: str


class StateBulkUpdate(BaseModel):
    items: list[StateBulkUpdateItem] = Field(..., min_length=1, max_length=100)


class StateBulkCreate(BaseModel):
    branch_id: str
    items: list[StateCreate] = Field(..., min_length=1, max_length=100)


# ══════════════════════════════════════════════════════════════════════════════
# Pydantic models — City
# ══════════════════════════════════════════════════════════════════════════════

class CityCreate(BaseModel):
    city_name:     str  = Field(..., min_length=2, max_length=150)
    city_code:     str  = Field(..., min_length=1, max_length=20)
    city_pin_code: str | None = Field(None, max_length=10)
    state_id:      str  = Field(..., description="State UUID (must belong to your company)")
    branch_id:     str  = Field(..., description="Branch UUID this city belongs to")
    is_active:     bool = True


class CityUpdate(BaseModel):
    city_name:     str | None  = Field(None, min_length=2, max_length=150)
    city_code:     str | None  = Field(None, min_length=1, max_length=20)
    city_pin_code: str | None  = Field(None, max_length=10)
    state_id:      str | None  = None
    is_active:     bool | None = None


class CityBulkUpdateItem(CityUpdate):
    city_id: str


class CityBulkUpdate(BaseModel):
    items: list[CityBulkUpdateItem] = Field(..., min_length=1, max_length=200)


class CityBulkCreate(BaseModel):
    branch_id: str
    items: list[CityCreate] = Field(..., min_length=1, max_length=200)


# ══════════════════════════════════════════════════════════════════════════════
# Pydantic models — Transport
# ══════════════════════════════════════════════════════════════════════════════

class TransportCreate(BaseModel):
    transport_code:      str  = Field(..., min_length=1, max_length=50)
    transport_name:      str  = Field(..., min_length=2, max_length=255)
    branch_id:           str  = Field(..., description="Branch UUID")
    gstin:               str | None = Field(None, max_length=15)
    mobile_number_owner: list[dict[str, str]] = Field(
        default=[],
        examples=[[{"name": "Owner", "mobile": "9876543210"}]],
        description='Array of {"name":"...","mobile":"..."}'
    )
    website:   str | None = None
    address:   str | None = None
    metadata:  dict[str, Any] = {}
    is_active: bool = True


class TransportUpdate(BaseModel):
    transport_name:      str | None = Field(None, min_length=2, max_length=255)
    transport_code:      str | None = Field(None, min_length=1, max_length=50)
    gstin:               str | None = Field(None, max_length=15)
    mobile_number_owner: list[dict[str, str]] | None = None
    website:             str | None = None
    address:             str | None = None
    metadata:            dict[str, Any] | None = None
    is_active:           bool | None = None


class TransportBulkUpdateItem(TransportUpdate):
    transport_id: str


class TransportBulkUpdate(BaseModel):
    items: list[TransportBulkUpdateItem] = Field(..., min_length=1, max_length=100)


class TransportBulkCreate(BaseModel):
    branch_id: str
    items: list[TransportCreate] = Field(..., min_length=1, max_length=100)


# ══════════════════════════════════════════════════════════════════════════════
# Pydantic models — City-wise Transport
# ══════════════════════════════════════════════════════════════════════════════

class CityTransportCreate(BaseModel):
    city_id:       str = Field(..., description="City UUID (must belong to your company)")
    transport_id:  str = Field(..., description="Transport UUID (must belong to your company)")
    branch_id:     str = Field(..., description="Branch UUID")
    branch_mobile: list[dict[str, str]] = Field(
        default=[],
        examples=[[{"label": "booking", "mobile": "9876543210"}]],
        description='Array of {"label":"...","mobile":"..."}'
    )
    address:      str | None = None
    manager_name: str | None = Field(None, max_length=255)
    is_active:    bool = True


class CityTransportUpdate(BaseModel):
    branch_mobile: list[dict[str, str]] | None = None
    address:       str | None = None
    manager_name:  str | None = Field(None, max_length=255)
    is_active:     bool | None = None


class CityTransportBulkUpdateItem(CityTransportUpdate):
    id: str


class CityTransportBulkUpdate(BaseModel):
    items: list[CityTransportBulkUpdateItem] = Field(..., min_length=1, max_length=200)


class CityTransportBulkCreate(BaseModel):
    branch_id: str
    items: list[CityTransportCreate] = Field(..., min_length=1, max_length=200)


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — STATE
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/states", status_code=201, summary="Create a state")
def api_create_state(body: StateCreate, current_user: dict = Depends(get_current_user)):
    company_id = current_user["company_id"]
    data = body.model_dump(exclude={"branch_id"})
    result = create_state(company_id, body.branch_id, data, created_by=current_user.get("sub"))
    return {"message": "State created.", "state": result}


@router.post("/states/bulk", status_code=201, summary="Bulk create states")
def api_bulk_create_states(body: StateBulkCreate, current_user: dict = Depends(get_current_user)):
    company_id = current_user["company_id"]
    items = [i.model_dump(exclude={"branch_id"}) for i in body.items]
    result = bulk_create_states(company_id, body.branch_id, items, created_by=current_user.get("sub"))
    return result


@router.get("/states", summary="List states")
def api_list_states(
    branch_id: str | None = Query(None),
    is_active: bool | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    states = list_states(current_user["company_id"], branch_id, is_active)
    return {"count": len(states), "states": states}


@router.get("/states/{state_id}", summary="Get a state")
def api_get_state(state_id: str, current_user: dict = Depends(get_current_user)):
    state = get_state(state_id, current_user["company_id"])
    if not state:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"State '{state_id}' not found.")
    return state


@router.patch("/states/{state_id}", summary="Update a state")
def api_update_state(state_id: str, body: StateUpdate, current_user: dict = Depends(get_current_user)):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update.")
    result = update_state(state_id, current_user["company_id"], data, updated_by=current_user.get("sub"))
    return {"message": "State updated.", "state": result}


@router.patch("/states/bulk", summary="Bulk update states")
def api_bulk_update_states(body: StateBulkUpdate, current_user: dict = Depends(get_current_user)):
    items = [i.model_dump(exclude_none=True) for i in body.items]
    result = bulk_update_states(current_user["company_id"], items, updated_by=current_user.get("sub"))
    return result


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — CITY
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/cities", status_code=201, summary="Create a city")
def api_create_city(body: CityCreate, current_user: dict = Depends(get_current_user)):
    company_id = current_user["company_id"]
    data = body.model_dump(exclude={"branch_id"})
    result = create_city(company_id, body.branch_id, data, created_by=current_user.get("sub"))
    return {"message": "City created.", "city": result}


@router.post("/cities/bulk", status_code=201, summary="Bulk create cities")
def api_bulk_create_cities(body: CityBulkCreate, current_user: dict = Depends(get_current_user)):
    company_id = current_user["company_id"]
    items = [i.model_dump(exclude={"branch_id"}) for i in body.items]
    result = bulk_create_cities(company_id, body.branch_id, items, created_by=current_user.get("sub"))
    return result


@router.get("/cities", summary="List cities")
def api_list_cities(
    branch_id:   str | None  = Query(None),
    state_id:    str | None  = Query(None),
    is_active:   bool | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    cities = list_cities(current_user["company_id"], branch_id, state_id, is_active)
    return {"count": len(cities), "cities": cities}


@router.get("/cities/{city_id}", summary="Get a city")
def api_get_city(city_id: str, current_user: dict = Depends(get_current_user)):
    city = get_city(city_id, current_user["company_id"])
    if not city:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"City '{city_id}' not found.")
    return city


@router.patch("/cities/{city_id}", summary="Update a city")
def api_update_city(city_id: str, body: CityUpdate, current_user: dict = Depends(get_current_user)):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update.")
    result = update_city(city_id, current_user["company_id"], data, updated_by=current_user.get("sub"))
    return {"message": "City updated.", "city": result}


@router.patch("/cities/bulk", summary="Bulk update cities")
def api_bulk_update_cities(body: CityBulkUpdate, current_user: dict = Depends(get_current_user)):
    items = [i.model_dump(exclude_none=True) for i in body.items]
    result = bulk_update_cities(current_user["company_id"], items, updated_by=current_user.get("sub"))
    return result


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — TRANSPORT
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/transports", status_code=201, summary="Create a transport")
def api_create_transport(body: TransportCreate, current_user: dict = Depends(get_current_user)):
    company_id = current_user["company_id"]
    data = body.model_dump(exclude={"branch_id"})
    result = create_transport(company_id, body.branch_id, data, created_by=current_user.get("sub"))
    return {"message": "Transport created.", "transport": result}


@router.post("/transports/bulk", status_code=201, summary="Bulk create transports")
def api_bulk_create_transports(body: TransportBulkCreate, current_user: dict = Depends(get_current_user)):
    company_id = current_user["company_id"]
    items = [i.model_dump(exclude={"branch_id"}) for i in body.items]
    result = bulk_create_transports(company_id, body.branch_id, items, created_by=current_user.get("sub"))
    return result


@router.get("/transports", summary="List transports")
def api_list_transports(
    branch_id:    str | None  = Query(None),
    is_active:    bool | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    transports = list_transports(current_user["company_id"], branch_id, is_active)
    return {"count": len(transports), "transports": transports}


@router.get("/transports/{transport_id}", summary="Get a transport")
def api_get_transport(transport_id: str, current_user: dict = Depends(get_current_user)):
    t = get_transport(transport_id, current_user["company_id"])
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Transport '{transport_id}' not found.")
    return t


@router.patch("/transports/{transport_id}", summary="Update a transport")
def api_update_transport(transport_id: str, body: TransportUpdate, current_user: dict = Depends(get_current_user)):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update.")
    result = update_transport(transport_id, current_user["company_id"], data, updated_by=current_user.get("sub"))
    return {"message": "Transport updated.", "transport": result}


@router.patch("/transports/bulk", summary="Bulk update transports")
def api_bulk_update_transports(body: TransportBulkUpdate, current_user: dict = Depends(get_current_user)):
    items = [i.model_dump(exclude_none=True) for i in body.items]
    result = bulk_update_transports(current_user["company_id"], items, updated_by=current_user.get("sub"))
    return result


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — CITY-WISE TRANSPORT
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/city-transports", status_code=201, summary="Link a transport to a city")
def api_create_city_transport(body: CityTransportCreate, current_user: dict = Depends(get_current_user)):
    company_id = current_user["company_id"]
    data = body.model_dump(exclude={"branch_id"})
    result = create_city_transport(company_id, body.branch_id, data, created_by=current_user.get("sub"))
    return {"message": "City-transport link created.", "city_transport": result}


@router.post("/city-transports/bulk", status_code=201, summary="Bulk link transports to cities")
def api_bulk_create_city_transports(body: CityTransportBulkCreate, current_user: dict = Depends(get_current_user)):
    company_id = current_user["company_id"]
    items = [i.model_dump(exclude={"branch_id"}) for i in body.items]
    result = bulk_create_city_transports(company_id, body.branch_id, items, created_by=current_user.get("sub"))
    return result


@router.get("/city-transports", summary="List city-transport links")
def api_list_city_transports(
    branch_id:    str | None  = Query(None),
    city_id:      str | None  = Query(None),
    transport_id: str | None  = Query(None),
    is_active:    bool | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    links = list_city_transports(current_user["company_id"], branch_id, city_id, transport_id, is_active)
    return {"count": len(links), "city_transports": links}


@router.get("/city-transports/{id}", summary="Get a city-transport link")
def api_get_city_transport(id: str, current_user: dict = Depends(get_current_user)):
    link = get_city_transport(id, current_user["company_id"])
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"City-transport link '{id}' not found.")
    return link


@router.patch("/city-transports/{id}", summary="Update a city-transport link")
def api_update_city_transport(id: str, body: CityTransportUpdate, current_user: dict = Depends(get_current_user)):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update.")
    result = update_city_transport(id, current_user["company_id"], data, updated_by=current_user.get("sub"))
    return {"message": "City-transport link updated.", "city_transport": result}


@router.patch("/city-transports/bulk", summary="Bulk update city-transport links")
def api_bulk_update_city_transports(body: CityTransportBulkUpdate, current_user: dict = Depends(get_current_user)):
    items = [i.model_dump(exclude_none=True) for i in body.items]
    result = bulk_update_city_transports(current_user["company_id"], items, updated_by=current_user.get("sub"))
    return result
