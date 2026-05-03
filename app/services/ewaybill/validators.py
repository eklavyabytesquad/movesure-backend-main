"""
Input validators for EWay Bill payloads.
All functions raise ValueError on bad input.
"""
import re

# ── Regexes ──────────────────────────────────────────────────────────────────
GSTIN_REGEX = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
)
VEHICLE_REGEX = re.compile(r"^[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{4}$")
VEHICLE_TEMP_REGEX = re.compile(r"^TM[A-Z0-9]{6}$")

VALID_DOC_TYPES = {
    "Tax Invoice", "Bill of Supply", "Bill of Entry",
    "Delivery Challan", "Credit Note", "Others",
}
VALID_TRANSPORT_MODES = {"Road", "Rail", "Air", "Ship", "In Transit"}

# mode_of_transport (numeric, used in extend/CEWB)
# 1=Road 2=Rail 3=Air 4=Ship 5=In Transit
_MODE_CONSIGNMENT: dict[str, tuple[str, str | None]] = {
    "1": ("M", ""),
    "2": ("M", ""),
    "3": ("M", ""),
    "4": ("M", ""),
    "5": ("T", None),  # transit_type required
}
_VALID_TRANSIT_TYPES = {"R", "W", "O"}


# ─────────────────────────────────────────────────────────────────────────────

def validate_gstin(gstin: str, field: str = "gstin") -> None:
    if gstin != "URP" and not GSTIN_REGEX.match(gstin):
        raise ValueError(f"Invalid GSTIN format for {field}: {gstin}")


def validate_vehicle_number(vehicle: str) -> str:
    """Normalise and validate vehicle number; return normalised form."""
    vehicle = vehicle.upper().replace(" ", "")
    if not (VEHICLE_REGEX.match(vehicle) or VEHICLE_TEMP_REGEX.match(vehicle)):
        raise ValueError(f"Invalid vehicle_number format: {vehicle}")
    return vehicle


def validate_generate_payload(payload: dict) -> None:
    """Full validation of generate-EWB payload."""
    required = [
        "userGstin", "supply_type", "sub_supply_type", "document_type",
        "document_number", "document_date", "gstin_of_consignor",
        "gstin_of_consignee", "pincode_of_consignor", "state_of_consignor",
        "pincode_of_consignee", "state_of_supply", "taxable_amount",
        "total_invoice_value", "transportation_mode", "transportation_distance",
        "itemList",
    ]
    missing = [f for f in required if payload.get(f) in (None, "", [])]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

    validate_gstin(payload["userGstin"], "userGstin")
    for f in ("gstin_of_consignor", "gstin_of_consignee"):
        validate_gstin(payload[f], f)

    if payload["document_type"] not in VALID_DOC_TYPES:
        raise ValueError(
            f"Invalid document_type '{payload['document_type']}'. "
            f"Valid: {', '.join(sorted(VALID_DOC_TYPES))}"
        )
    if payload["transportation_mode"] not in VALID_TRANSPORT_MODES:
        raise ValueError(
            f"Invalid transportation_mode '{payload['transportation_mode']}'. "
            f"Valid: {', '.join(sorted(VALID_TRANSPORT_MODES))}"
        )
    dist = int(payload["transportation_distance"])
    if not (0 <= dist <= 4000):
        raise ValueError("transportation_distance must be 0–4000 km")

    mode = payload["transportation_mode"]
    if mode == "Road":
        vehicle = payload.get("vehicle_number", "").upper()
        if not vehicle:
            raise ValueError("vehicle_number is required for Road transport")
        validate_vehicle_number(vehicle)
    elif mode in ("Rail", "Air", "Ship"):
        if not payload.get("transporter_document_number"):
            raise ValueError(f"transporter_document_number is required for {mode} transport")

    items = payload["itemList"]
    if not isinstance(items, list) or len(items) == 0:
        raise ValueError("itemList must be a non-empty array")
    if len(items) > 250:
        raise ValueError("itemList cannot exceed 250 items")

    for idx, item in enumerate(items, 1):
        if not item.get("product_name") and not item.get("product_description"):
            raise ValueError(f"Item {idx}: product_name or product_description required")
        hsn = str(item.get("hsn_code", ""))
        if not hsn.isdigit() or not (4 <= len(hsn) <= 8):
            raise ValueError(f"Item {idx}: hsn_code must be 4–8 numeric digits")
        if float(item.get("quantity", 0)) <= 0:
            raise ValueError(f"Item {idx}: quantity must be > 0")

    taxable = float(payload.get("taxable_amount", 0))
    total   = float(payload["total_invoice_value"])
    computed = (
        taxable
        + float(payload.get("cgst_amount", 0))
        + float(payload.get("sgst_amount", 0))
        + float(payload.get("igst_amount", 0))
        + float(payload.get("cess_amount", 0))
        + float(payload.get("other_amount", 0))
        + float(payload.get("cess_non_advol_amount", 0))
    )
    if computed > total + 2:
        raise ValueError(
            f"total_invoice_value ({total}) must be >= sum of components ({computed:.2f})"
        )


def validate_consolidate_payload(payload: dict) -> None:
    required = [
        "userGstin", "place_of_consignor", "state_of_consignor",
        "vehicle_number", "mode_of_transport", "transporter_document_number",
        "transporter_document_date", "data_source", "list_of_eway_bills",
    ]
    missing = [f for f in required if payload.get(f) in (None, "", [])]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")


def validate_extend_payload(payload: dict) -> dict:
    """Validate extend payload; return enriched payload with auto-filled fields."""
    required = [
        "userGstin", "eway_bill_number", "vehicle_number", "place_of_consignor",
        "state_of_consignor", "remaining_distance", "mode_of_transport",
        "extend_validity_reason", "from_pincode",
    ]
    missing = [f for f in required if payload.get(f) in (None, "")]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

    mode = str(payload["mode_of_transport"])
    if mode not in _MODE_CONSIGNMENT:
        raise ValueError(f"Invalid mode_of_transport '{mode}'. Must be 1–5.")

    expected_cs, _ = _MODE_CONSIGNMENT[mode]
    payload = dict(payload)
    payload["consignment_status"] = expected_cs

    if mode == "5":
        tt = payload.get("transit_type", "").upper()
        if tt not in _VALID_TRANSIT_TYPES:
            raise ValueError(f"transit_type must be R/W/O for In Transit mode; got '{tt}'")
        payload["transit_type"] = tt
    else:
        payload["transit_type"] = ""

    payload["eway_bill_number"] = int(payload["eway_bill_number"])
    payload["from_pincode"] = int(payload["from_pincode"])
    return payload


def normalise_generate_payload(raw: dict) -> dict:
    """Accept snake_case / camelCase keys; clamp negative rates."""
    payload = dict(raw)
    if "user_gstin" in payload and "userGstin" not in payload:
        payload["userGstin"] = payload.pop("user_gstin")
    if "item_list" in payload and "itemList" not in payload:
        payload["itemList"] = payload.pop("item_list")
    for item in payload.get("itemList", []):
        if not item.get("product_name") and item.get("product_description"):
            item["product_name"] = item["product_description"]
        for rk in ("cgst_rate", "sgst_rate", "igst_rate"):
            if float(item.get(rk, 0)) < 0:
                item[rk] = 0
    if payload.get("vehicle_number"):
        payload["vehicle_number"] = payload["vehicle_number"].upper().replace(" ", "")
    return payload
