"""
GSTIN / transporter lookup and distance helpers.
Read-only — no DB writes.
"""
import logging

from app.services.ewaybill.nic_client import nic_get
from app.services.ewaybill.validators import validate_gstin

logger = logging.getLogger("movesure.ewaybill.lookup")


def get_gstin_details(user_gstin: str, gstin: str) -> dict:
    """Live NIC GSTIN lookup via Masters India GetGSTINDetails action."""
    validate_gstin(user_gstin, "userGstin")
    validate_gstin(gstin, "gstin")

    data = nic_get(
        "getEwayBillData/",
        {"action": "GetGSTINDetails", "userGstin": user_gstin, "gstin": gstin},
    )
    results = data.get("results", {})
    msg = results.get("message", {})
    return {
        "status":                 "success",
        "gstin_of_taxpayer":      msg.get("gstin"),
        "trade_name":             msg.get("tradeName"),
        "legal_name_of_business": msg.get("legalName"),
        "address1":               msg.get("addr1"),
        "address2":               msg.get("addr2"),
        "state_name":             msg.get("stateCode"),
        "pincode":                msg.get("pinCode"),
        "taxpayer_type":          msg.get("taxpayerType"),
        "taxpayer_status":        msg.get("status"),
        "block_status":           msg.get("blkStatus"),
    }


def get_transporter_details(user_gstin: str, gstin: str) -> dict:
    """Alias for get_gstin_details with a transporter-specific message."""
    result = get_gstin_details(user_gstin, gstin)
    result["message"] = "Transporter details retrieved successfully"
    return result


def get_distance(from_pincode: str, to_pincode: str) -> dict:
    """Return road distance (km) between two Indian pincodes."""
    for pin, label in ((from_pincode, "fromPincode"), (to_pincode, "toPincode")):
        if not pin.isdigit() or len(pin) != 6:
            raise ValueError(f"{label} must be exactly 6 digits: '{pin}'")

    data = nic_get("distance/", {"fromPincode": from_pincode, "toPincode": to_pincode})
    results = data.get("results", data)
    msg = results.get("message", {})
    dist = msg.get("distance") if isinstance(msg, dict) else results.get("distance")
    return {
        "status":       "success",
        "distance":     dist,
        "from_pincode": from_pincode,
        "to_pincode":   to_pincode,
    }
