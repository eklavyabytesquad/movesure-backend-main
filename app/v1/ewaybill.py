"""
E-Way Bill Router  -  /v1/ewaybill/*
--------------------------------------
All endpoints proxy Masters India GSP API calls.
Token is validated/refreshed automatically on every request via the token_service layer.
Auth context (company_id, branch_id, user_id) is extracted from the JWT and passed to
service functions so every mutating operation is persisted to the DB.

Endpoints:
  GET  /ewaybill/token/status           - show current JWT status (no refresh)
  POST /ewaybill/token/refresh          - force token refresh
  GET  /ewaybill/validate               - fetch EWB details by number + save to DB
  GET  /ewaybill/gstin                  - GSTIN validator / lookup
  GET  /ewaybill/transporter            - transporter GSTIN lookup
  GET  /ewaybill/distance               - distance between pincodes
  POST /ewaybill/generate               - generate a new EWB + save to DB
  POST /ewaybill/consolidate            - consolidated EWB + save to DB
  POST /ewaybill/transporter-update     - assign/change transporter + save to DB
  POST /ewaybill/transporter-update-pdf - assign transporter + fetch PDF + save to DB
  POST /ewaybill/extend                 - extend EWB validity + save to DB
  GET  /ewaybill/settings               - get company EWB settings (GSTIN etc.)
  POST /ewaybill/settings               - create / update company EWB settings
  DELETE /ewaybill/settings             - deactivate company EWB settings
"""

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt, JWTError
from pydantic import BaseModel

from app.middleware.auth import get_current_user
from app.services.ewaybill.token_service import (
    get_jwt_token,
    get_token_status,
)
from app.services.ewaybill.exceptions import EWayBillError
from app.services.ewaybill.lookup_service import (
    get_gstin_details,
    get_transporter_details,
    get_distance,
)
from app.services.ewaybill.records_service import fetch_ewaybill
from app.services.ewaybill.generate_service import (
    generate_ewaybill,
    generate_consolidated_ewaybill,
)
from app.services.ewaybill.transporter_service import (
    update_transporter,
    update_transporter_with_pdf,
)
from app.services.ewaybill.extend_service import extend_ewaybill
from app.services.ewaybill.settings_service import (
    get_settings,
    get_company_gstin,
    upsert_settings,
    delete_settings,
)
from app.services.ewaybill.token_service import MI_USERNAME
from app.services.ewaybill.pdf_service import generate_ewb_pdf_from_record
from app.services.ewaybill.db import get_ewb_record, get_validation_history, get_ewbs_by_bilty, get_ewbs_by_challan, get_ewbs_by_challan_no, get_all_validated_ewbs, get_cewbs_by_trip

logger = logging.getLogger("movesure.ewaybill")

router = APIRouter(prefix="/ewaybill", tags=["E-Way Bill"])


# ----------------------------------------------------------------------------
# Error wrapper
# ----------------------------------------------------------------------------

def _handle_error(exc: Exception) -> None:
    if isinstance(exc, EWayBillError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": str(exc), "nic_code": exc.nic_code, "type": "nic_error"},
        )
    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": str(exc), "type": "validation_error"},
        )
    logger.exception("Unexpected EWB service error: %s", exc)
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={"error": str(exc), "type": "upstream_error"},
    )


def _ctx(user: dict) -> tuple[str, str, str]:
    """Extract (company_id, branch_id, user_id) from JWT payload."""
    return (
        user.get("company_id", ""),
        user.get("branch_id", ""),
        user.get("user_id") or user.get("sub", ""),
    )


def _get_gstin(company_id: str) -> str:
    """Return stored company GSTIN or raise 400 with onboarding hint."""
    try:
        return get_company_gstin(company_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "EWB settings not configured for this company.",
                "hint":  "POST /v1/ewaybill/settings with your company_gstin first.",
            },
        )


# ============================================================================
# TOKEN MANAGEMENT  (no auth required)
# ============================================================================

@router.get("/token/status", summary="Check Masters India JWT token status", response_model=None)
def token_status():
    """Returns current token validity without triggering a refresh."""
    return get_token_status()


@router.post("/token/refresh", summary="Force-refresh Masters India JWT token", response_model=None)
def token_refresh():
    """Bypasses cache and fetches a fresh token from Masters India."""
    token = get_jwt_token()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "Failed to refresh token from Masters India", "type": "auth_error"},
        )
    return {"status": "success", "message": "Token refreshed successfully", **get_token_status()}


# ============================================================================
# E-WAY BILL VALIDATION / FETCH
# ============================================================================

@router.get("/validate", summary="Fetch E-Way Bill details by EWB number", response_model=None)
def validate_ewaybill(
    eway_bill_number: str = Query(..., description="12-digit E-Way Bill number"),
    bilty_id: str | None = Query(None, description="Optional bilty UUID to link this EWB"),
    force_refresh: bool = Query(
        False,
        description=(
            "Set true to always call NIC for a fresh status check. "
            "Default (false) returns the cached DB record if already validated — "
            "prevents redundant NIC calls when the validate tab is opened repeatedly."
        ),
    ),
    user: dict = Depends(get_current_user),
):
    """
    Retrieves EWB details and saves to DB.

    **Default behaviour (force_refresh=false):**
    If the EWB already exists in `ewb_records`, returns the cached data instantly
    — no NIC call is made.  Response includes `"source": "cache"` and the full
    validation history summary.  Use this when the UI loads the validate tab on
    every navigation (prevents spamming NIC).

    **force_refresh=true:**
    Always calls NIC, saves a new version to `ewb_validation_log`, and updates
    `ewb_records` with the latest state.  Use this for the explicit "Re-validate"
    / "Refresh from NIC" button.
    """
    company_id, branch_id, user_id = _ctx(user)
    gstin = _get_gstin(company_id)
    try:
        return fetch_ewaybill(
            eway_bill_number, gstin,
            company_id=company_id, branch_id=branch_id,
            user_id=user_id, bilty_id=bilty_id,
            force_refresh=force_refresh,
        )
    except Exception as exc:
        _handle_error(exc)


@router.get(
    "/validation-history",
    summary="Get full validation history for an E-Way Bill",
    response_model=None,
)
def ewb_validation_history(
    eway_bill_number: str = Query(..., description="12-digit E-Way Bill number"),
    user: dict = Depends(get_current_user),
):
    """
    Returns a versioned history of every NIC validation check for the given EWB.

    Useful for:
    - Showing an **"Already Validated"** badge on the frontend (check `is_previously_validated`)
    - Displaying how many times an EWB was checked (`total_validations`)
    - Auditing status changes over time (ACTIVE → EXTENDED → CANCELLED)

    Each `history` entry represents one NIC fetch:

    | Field | Description |
    |---|---|
    | `version_no` | Sequential count — v1 = first check, v2 = second, etc. |
    | `nic_status` | NIC-returned status at that moment (ACTIVE / CANCELLED / etc.) |
    | `valid_upto` | Validity timestamp returned at that check |
    | `vehicle_number` | Vehicle on record at that check |
    | `transporter_id` | Transporter GSTIN at that check |
    | `error_code` | NIC error code if the check failed (e.g. "338") |
    | `error_description` | Human-readable NIC error message |
    | `triggered_by` | What triggered the check: `manual` / `auto` / `on_generate` |
    | `validated_at` | UTC timestamp of the check |

    **Frontend badge usage:**
    ```js
    const { is_previously_validated, total_validations } = await fetchValidationHistory(ewbNumber);
    // Show: "Validated 3 times — last checked 2 minutes ago"
    ```
    """
    company_id, _, _ = _ctx(user)

    # Current record summary
    record = get_ewb_record(company_id, eway_bill_number)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": f"EWB {eway_bill_number} not found in your company records.",
                "hint":  "Call GET /v1/ewaybill/validate first to fetch and save it.",
            },
        )

    history = get_validation_history(company_id, eway_bill_number)
    latest = history[0] if history else None

    return {
        "status":                  "success",
        "eway_bill_number":        eway_bill_number,
        # ── Summary (use these for the frontend badge) ──
        "is_previously_validated": len(history) > 0,
        "total_validations":       len(history),
        "latest_version_no":       latest["version_no"] if latest else None,
        "latest_nic_status":       latest["nic_status"] if latest else None,
        "latest_validated_at":     latest["validated_at"] if latest else None,
        # ── Current EWB state ──
        "current_ewb_status":      record.get("ewb_status"),
        "current_valid_upto":      record.get("valid_upto"),
        "ewb_id":                  record.get("ewb_id"),
        # ── Full versioned history ──
        "history":                 history,
    }


# ============================================================================
# FETCH EWB RECORDS BY BILTY / CHALLAN
# ============================================================================

@router.get("/records", summary="List saved EWB records for a bilty, challan, or all", response_model=None)
def list_ewb_records(
    bilty_id: str | None = Query(None, description="Bilty UUID — returns EWBs for this bilty"),
    challan_id: str | None = Query(None, description="Challan UUID — returns all EWBs linked to bilties in this challan"),
    challan_no: str | None = Query(None, description="Challan number e.g. 'A00003' — resolves to UUID automatically"),
    all: bool = Query(False, description="Set true to return all validated EWBs for your branch"),
    user: dict = Depends(get_current_user),
):
    """
    Fetch E-Way Bill records from `ewb_records`.

    Modes (pass exactly one):
    - `bilty_id` — EWBs for a single bilty/LR
    - `challan_id` — EWBs for all bilties in a challan (UUID)
    - `challan_no` — EWBs for all bilties in a challan (e.g. 'A00003')
    - `all=true` — Every validated EWB for your branch

    **Note**: EWBs are linked to bilties, not directly to challans.
    The challan queries work by finding all bilties in the challan first.
    """
    company_id, branch_id, _ = _ctx(user)

    if not any([bilty_id, challan_id, challan_no, all]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Provide one of: bilty_id, challan_id, challan_no, or all=true"},
        )

    if bilty_id:
        results = get_ewbs_by_bilty(company_id, bilty_id)
        filter_used = f"bilty_id={bilty_id}"
    elif challan_no:
        results = get_ewbs_by_challan_no(company_id, challan_no)
        filter_used = f"challan_no={challan_no}"
    elif challan_id:
        results = get_ewbs_by_challan(company_id, challan_id)
        filter_used = f"challan_id={challan_id}"
    else:
        results = get_all_validated_ewbs(company_id, branch_id)
        filter_used = "all"

    return {
        "status":       "success",
        "filter":       filter_used,
        "count":        len(results),
        "records":      results,
    }


# ============================================================================
# GSTIN / TRANSPORTER LOOKUP  (read-only, no DB write)
# ============================================================================

@router.get("/gstin", summary="Validate and look up a GSTIN", response_model=None)
def gstin_details(
    gstin: str = Query(..., description="GSTIN to look up"),
    user: dict = Depends(get_current_user),
):
    """Live NIC lookup - returns taxpayer name, address, status, block status."""
    company_id, _, _ = _ctx(user)
    user_gstin = _get_gstin(company_id)
    try:
        return get_gstin_details(user_gstin, gstin)
    except Exception as exc:
        _handle_error(exc)


@router.get("/transporter", summary="Look up a transporter GSTIN", response_model=None)
def transporter_details(
    gstin: str = Query(..., description="Transporter GSTIN to look up"),
    user: dict = Depends(get_current_user),
):
    """Returns transporter name and details from NIC."""
    company_id, _, _ = _ctx(user)
    user_gstin = _get_gstin(company_id)
    try:
        return get_transporter_details(user_gstin, gstin)
    except Exception as exc:
        _handle_error(exc)


@router.get("/distance", summary="Get distance between two pincodes", response_model=None)
def distance_between_pincodes(
    fromPincode: str = Query(..., description="6-digit source pincode"),
    toPincode: str = Query(..., description="6-digit destination pincode"),
    _: dict = Depends(get_current_user),
):
    """Returns road distance (km) between two Indian pincodes."""
    try:
        return get_distance(fromPincode, toPincode)
    except Exception as exc:
        _handle_error(exc)


# ============================================================================
# GENERATE E-WAY BILL
# ============================================================================

class GenerateEWBRequest(BaseModel):
    model_config = {"extra": "allow"}

    supply_type: str
    sub_supply_type: str
    document_type: str
    document_number: str
    document_date: str                   # DD/MM/YYYY
    gstin_of_consignor: str
    gstin_of_consignee: str
    pincode_of_consignor: str
    state_of_consignor: str
    pincode_of_consignee: str
    state_of_supply: str
    taxable_amount: float
    total_invoice_value: float
    transportation_mode: str             # Road / Rail / Air / Ship / In Transit
    transportation_distance: int         # 0-4000 km
    itemList: list[dict[str, Any]]

    vehicle_number: str | None = None
    vehicle_type: str | None = "Regular"
    transporter_id: str | None = None
    transporter_name: str | None = None
    transporter_document_number: str | None = None
    transporter_document_date: str | None = None

    # Optional tax amounts
    cgst_amount: float = 0.0
    sgst_amount: float = 0.0
    igst_amount: float = 0.0
    cess_amount: float = 0.0
    other_amount: float = 0.0
    cess_non_advol_amount: float = 0.0

    # DB linking
    bilty_id: str | None = None


@router.post("/generate", summary="Generate a new E-Way Bill", response_model=None)
def generate_ewb(body: GenerateEWBRequest, user: dict = Depends(get_current_user)):
    """
    Creates a new E-Way Bill on NIC and saves to DB.

    Vehicle number format (Road mode): UP32AB1234 or TM[6 chars] for temp.
    """
    company_id, branch_id, user_id = _ctx(user)
    user_gstin = _get_gstin(company_id)
    payload = body.model_dump()
    payload["userGstin"] = user_gstin
    try:
        return generate_ewaybill(
            payload,
            company_id=company_id, branch_id=branch_id,
            user_id=user_id, bilty_id=body.bilty_id,
        )
    except Exception as exc:
        _handle_error(exc)


# ============================================================================
# CONSOLIDATED E-WAY BILL
# ============================================================================

class ConsolidatedEWBRequest(BaseModel):
    place_of_consignor: str
    state_of_consignor: str
    vehicle_number: str
    mode_of_transport: str
    transporter_document_number: str
    transporter_document_date: str       # DD/MM/YYYY
    data_source: str = "E"
    list_of_eway_bills: list             # list of EWB numbers (str) or objects
    trip_sheet_id: str | None = None     # optional — links CEWB to a trip sheet


@router.post("/consolidate", summary="Generate a Consolidated E-Way Bill", response_model=None)
def consolidate_ewb(body: ConsolidatedEWBRequest, user: dict = Depends(get_current_user)):
    """
    Merges multiple individual EWBs into one Consolidated EWB for a single vehicle.

    list_of_eway_bills accepts flat strings or objects:
      ["321012345678", "321012345679"]
      [{"eway_bill_number": "321012345678"}, ...]
    """
    company_id, branch_id, user_id = _ctx(user)
    user_gstin = _get_gstin(company_id)
    payload = body.model_dump()
    payload["userGstin"] = user_gstin
    try:
        return generate_consolidated_ewaybill(
            payload,
            company_id=company_id, branch_id=branch_id, user_id=user_id,
            trip_sheet_id=body.trip_sheet_id,
        )
    except Exception as exc:
        _handle_error(exc)


# ============================================================================
# FETCH CONSOLIDATED EWBs
# ============================================================================

@router.get("/consolidated", summary="List consolidated EWBs for a trip sheet", response_model=None)
def list_consolidated_ewbs(
    trip_sheet_id: str = Query(..., description="Trip sheet UUID (challan_trip_sheet.trip_sheet_id)"),
    user: dict = Depends(get_current_user),
):
    """
    Returns all consolidated EWBs created for a trip sheet.

    Each record includes:
    - `cewb_number`   — the NIC-assigned consolidated EWB number
    - `pdf_url`       — direct download link for the CEWB PDF
    - `cewb_status`   — ACTIVE / CANCELLED / EXPIRED
    - `vehicle_number`, `cewb_date`, `ewb_numbers` (member EWB list)
    """
    company_id, _, _ = _ctx(user)
    records = get_cewbs_by_trip(company_id, trip_sheet_id)
    return {
        "status":        "success",
        "trip_sheet_id": trip_sheet_id,
        "count":         len(records),
        "consolidated":  records,
    }


# ============================================================================
# TRANSPORTER UPDATE
# ============================================================================

class TransporterUpdateRequest(BaseModel):
    eway_bill_number: int | str
    transporter_id: str
    transporter_name: str | None = None


@router.post("/transporter-update", summary="Assign or change transporter on an EWB", response_model=None)
def transporter_update(body: TransporterUpdateRequest, user: dict = Depends(get_current_user)):
    """Updates the transporter assigned to an existing EWB and saves event to DB."""
    company_id, branch_id, user_id = _ctx(user)
    user_gstin = _get_gstin(company_id)
    payload = body.model_dump()
    payload["userGstin"] = user_gstin
    try:
        return update_transporter(
            payload,
            company_id=company_id, branch_id=branch_id, user_id=user_id,
        )
    except Exception as exc:
        _handle_error(exc)


@router.post("/transporter-update-pdf", summary="Assign transporter and fetch updated PDF", response_model=None)
def transporter_update_pdf(body: TransporterUpdateRequest, user: dict = Depends(get_current_user)):
    """Same as /transporter-update but makes a second call to fetch the updated PDF."""
    company_id, branch_id, user_id = _ctx(user)
    user_gstin = _get_gstin(company_id)
    payload = body.model_dump()
    payload["userGstin"] = user_gstin
    try:
        return update_transporter_with_pdf(
            payload,
            company_id=company_id, branch_id=branch_id, user_id=user_id,
        )
    except Exception as exc:
        _handle_error(exc)


# ============================================================================
# EXTEND E-WAY BILL VALIDITY
# ============================================================================

class ExtendEWBRequest(BaseModel):
    eway_bill_number: int | str
    vehicle_number: str
    place_of_consignor: str
    state_of_consignor: str
    remaining_distance: int
    mode_of_transport: str               # "1" to "5"
    extend_validity_reason: str
    extend_remarks: str | None = None
    from_pincode: int | str
    transit_type: str | None = ""        # R / W / O  (mode 5 only)
    address_line1: str | None = None
    address_line2: str | None = None
    address_line3: str | None = None


@router.post("/extend", summary="Extend E-Way Bill validity", response_model=None)
def extend_ewb(body: ExtendEWBRequest, user: dict = Depends(get_current_user)):
    """
    Extends EWB validity and saves updated status + event to DB.

    NIC rules:
    - Extension window: 8 hours before to 8 hours after expiry.
    - Only the current transporter (or generator if none assigned) can extend.

    mode_of_transport: 1=Road 2=Rail 3=Air 4=Ship 5=In Transit
    transit_type (mode 5 only): R=Road W=Warehouse O=Others
    """
    company_id, branch_id, user_id = _ctx(user)
    user_gstin = _get_gstin(company_id)
    payload = body.model_dump()
    payload["userGstin"] = user_gstin
    try:
        return extend_ewaybill(
            payload,
            company_id=company_id, branch_id=branch_id, user_id=user_id,
        )
    except Exception as exc:
        _handle_error(exc)


# ============================================================================
# COMPANY EWB SETTINGS
# ============================================================================

class EWBSettingsRequest(BaseModel):
    company_gstin: str                      # 15-char GSTIN — the only required field


@router.get("/settings", summary="Get company EWB settings", response_model=None)
def get_ewb_settings(user: dict = Depends(get_current_user)):
    """
    Returns the EWB configuration for the caller's company.

    The most important field is `company_gstin` — it becomes the `userGstin`
    parameter on every NIC API call.  The Masters India account is fixed to
    `eklavyasingh9870@gmail.com` and cannot be changed.
    """
    company_id, _, _ = _ctx(user)
    row = get_settings(company_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "EWB settings not configured for this company.",
                "hint":  "POST /v1/ewaybill/settings with your company_gstin to set up.",
            },
        )
    # Never expose the raw MI password / credentials
    row.pop("mi_password", None)
    return {
        "status": "success",
        "data": row,
        "mi_account": MI_USERNAME,
    }


@router.post("/settings", summary="Create or update company EWB settings", response_model=None)
def save_ewb_settings(body: EWBSettingsRequest, user: dict = Depends(get_current_user)):
    """
    Save (create or update) EWB configuration for the caller's company.

    **Required:** `company_gstin` — the company's own 15-character GSTIN registered
    with the GST portal.  This GSTIN will be sent as `userGstin` on all NIC calls.

    The Masters India account used is **always** `eklavyasingh9870@gmail.com`.
    You do not need to supply credentials.
    """
    company_id, _, user_id = _ctx(user)
    try:
        row = upsert_settings(
            company_id=company_id,
            company_gstin=body.company_gstin,
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": str(exc)})
    return {
        "status":     "success",
        "message":    "EWB settings saved successfully.",
        "mi_account": MI_USERNAME,
        "data":       row,
    }


@router.delete("/settings", summary="Deactivate company EWB settings", response_model=None)
def remove_ewb_settings(user: dict = Depends(get_current_user)):
    """
    Soft-deactivates EWB settings for the company (sets `is_active = false`).
    Does NOT delete the row — the GSTIN history is preserved.
    """
    company_id, _, user_id = _ctx(user)
    delete_settings(company_id, user_id)
    return {"status": "success", "message": "EWB settings deactivated."}


# ============================================================================
# E-WAY BILL PDF PRINT
# ============================================================================

def _resolve_user_for_pdf(request: Request, token_param: str | None) -> dict:
    """
    Resolve the authenticated user for the PDF endpoint.
    Accepts the JWT from either:
      1. Authorization: Bearer <token>  header  (fetch() calls)
      2. ?token=<jwt>                   query   (browser window.open / <a href>)
    """
    JWT_SECRET    = os.getenv("JWT_SECRET", "change-me")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

    raw_token: str | None = None

    # Priority 1 — Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        raw_token = auth_header[7:].strip()

    # Priority 2 — query param (browser direct navigation)
    if not raw_token and token_param:
        raw_token = token_param.strip()

    if not raw_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")

    try:
        payload = jwt.decode(raw_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise ValueError("Not an access token")
        return payload
    except (JWTError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")


@router.get("/pdf", summary="Download print-ready PDF for an E-Way Bill", response_model=None)
def download_ewb_pdf(
    request: Request,
    eway_bill_number: str = Query(..., description="12-digit E-Way Bill number"),
    token: str | None = Query(None, description="JWT token (use when Authorization header cannot be set, e.g. direct browser link)"),
):
    """
    Returns a black & white print-ready PDF for the given EWB number.

    Accepts the JWT via **either**:
    - `Authorization: Bearer <token>` header  — for fetch() / axios calls
    - `?token=<jwt>` query parameter           — for direct browser links / window.open / <a href>

    The EWB data is loaded from `ewb_records` DB (if already saved), or fetched
    live from NIC, saved to DB, then converted to PDF.

    Frontend usage:
        // fetch() — Authorization header
        fetch('/v1/ewaybill/pdf?eway_bill_number=382241586928', { headers: { Authorization: 'Bearer ...' } })

        // Direct browser link — token in query string
        window.open(`/v1/ewaybill/pdf?eway_bill_number=382241586928&token=${jwt}`)
        <a href={`/v1/ewaybill/pdf?eway_bill_number=382241586928&token=${jwt}`} download>Download</a>
    """
    user = _resolve_user_for_pdf(request, token)
    company_id, branch_id, user_id = _ctx(user)

    # 1. Try DB first (fastest)
    record = get_ewb_record(company_id, eway_bill_number)

    if not record:
        # 2. Not in DB — fetch live from NIC and save
        gstin = _get_gstin(company_id)
        try:
            fetch_ewaybill(
                eway_bill_number, gstin,
                company_id=company_id, branch_id=branch_id, user_id=user_id,
            )
        except Exception as exc:
            _handle_error(exc)
        record = get_ewb_record(company_id, eway_bill_number)
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"EWB {eway_bill_number} not found."},
            )

    raw = record.get("raw_response") or {}
    try:
        pdf_bytes = generate_ewb_pdf_from_record(raw)
    except Exception as exc:
        logger.exception("PDF generation failed for EWB %s: %s", eway_bill_number, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "PDF generation failed.", "detail": str(exc)},
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="EWB_{eway_bill_number}.pdf"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )
