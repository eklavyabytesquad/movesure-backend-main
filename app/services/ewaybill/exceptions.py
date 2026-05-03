"""
EWay Bill custom exceptions.
"""
import re


class EWayBillError(Exception):
    """Raised when Masters India / NIC returns a business-level error."""

    def __init__(
        self,
        message: str,
        nic_code: str | None = None,
        raw: dict | None = None,
    ):
        super().__init__(message)
        self.nic_code = nic_code
        self.raw = raw


def parse_nic_error(message) -> tuple[str | None, str]:
    """Extract (nic_code, description) from NIC error like '338: Not authorised'."""
    if isinstance(message, str):
        m = re.match(r"^(\d+):\s*(.+)$", message.strip())
        if m:
            return m.group(1), m.group(2)
        return None, message
    return None, str(message)
