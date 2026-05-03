"""
E-Way Bill service package.

Component layout:
  exceptions.py          — EWayBillError, parse_nic_error
  validators.py          — GSTIN / vehicle / payload validators
  nic_client.py          — HTTP helpers (nic_get, nic_post)
  db.py                  — Supabase persistence helpers
  token_service.py       — Masters India JWT manager
  settings_service.py    — Per-company ewb_settings CRUD
  lookup_service.py      — GSTIN lookup, transporter lookup, distance (read-only)
  records_service.py     — Fetch/validate EWB + DB
  generate_service.py    — Generate EWB + Consolidated EWB + DB
  transporter_service.py — Transporter update + DB
  extend_service.py      — Extend validity + DB
  service.py             — Backward-compat re-exports
"""

from app.services.ewaybill.exceptions import EWayBillError, parse_nic_error
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
    get_settings_or_raise,
    get_company_gstin,
    upsert_settings,
    delete_settings,
)

__all__ = [
    "EWayBillError",
    "parse_nic_error",
    "fetch_ewaybill",
    "get_gstin_details",
    "get_transporter_details",
    "get_distance",
    "generate_ewaybill",
    "generate_consolidated_ewaybill",
    "update_transporter",
    "update_transporter_with_pdf",
    "extend_ewaybill",
    "get_settings",
    "get_settings_or_raise",
    "get_company_gstin",
    "upsert_settings",
    "delete_settings",
]


from app.services.ewaybill.exceptions import EWayBillError, parse_nic_error
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

__all__ = [
    "EWayBillError",
    "parse_nic_error",
    "fetch_ewaybill",
    "get_gstin_details",
    "get_transporter_details",
    "get_distance",
    "generate_ewaybill",
    "generate_consolidated_ewaybill",
    "update_transporter",
    "update_transporter_with_pdf",
    "extend_ewaybill",
]
