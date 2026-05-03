"""
HTTP client helpers for Masters India GSP API.
"""
import logging

import requests

from app.services.ewaybill.exceptions import EWayBillError, parse_nic_error
from app.services.ewaybill.token_service import get_auth_headers, MI_BASE_URL

logger = logging.getLogger("movesure.ewaybill.nic")


def _raise_if_nic_error(results: dict) -> None:
    code   = results.get("code", 200)
    status = results.get("status", "")
    if code == 204 or status == "No Content":
        raw_error = results.get("message", "Unknown NIC error")
        nic_code, description = parse_nic_error(raw_error)
        raise EWayBillError(description, nic_code=nic_code, raw=results)


def nic_get(endpoint: str, params: dict) -> dict:
    """GET against Masters India; raise on HTTP error or NIC business error."""
    url = MI_BASE_URL + endpoint
    logger.info("NIC GET %s | params=%s", endpoint, params)
    resp = requests.get(url, params=params, headers=get_auth_headers(), timeout=20)
    logger.info("NIC GET %s | HTTP %s | response=%s", endpoint, resp.status_code, resp.text)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", data)
    _raise_if_nic_error(results)
    return data


def nic_post(endpoint: str, payload: dict) -> dict:
    """POST against Masters India; raise on HTTP error or NIC business error."""
    url = MI_BASE_URL + endpoint
    logger.info("NIC POST %s | payload=%s", endpoint, payload)
    resp = requests.post(url, json=payload, headers=get_auth_headers(), timeout=30)
    logger.info("NIC POST %s | HTTP %s | response=%s", endpoint, resp.status_code, resp.text)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", data)
    _raise_if_nic_error(results)
    return data
