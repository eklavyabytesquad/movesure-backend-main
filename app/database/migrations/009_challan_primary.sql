-- ============================================================
-- Migration 009: Primary Challan per Branch
-- Adds is_primary flag to the challan table so each branch can
-- designate one open challan as the "active" challan that new
-- bilties are auto-assigned to.
-- ============================================================

ALTER TABLE challan
    ADD COLUMN IF NOT EXISTS is_primary BOOLEAN NOT NULL DEFAULT FALSE;

-- Only one primary open/active challan is allowed per branch at any time.
-- A dispatched or closed challan cannot be primary, so the partial
-- index enforces uniqueness only while the challan is still open.
CREATE UNIQUE INDEX IF NOT EXISTS uq_challan_primary
    ON challan(company_id, branch_id)
    WHERE is_primary = TRUE
      AND is_active  = TRUE
      AND status NOT IN ('DISPATCHED', 'ARRIVED_HUB', 'CLOSED');
