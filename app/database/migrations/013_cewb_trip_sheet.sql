-- ============================================================
-- Migration 013: Add trip_sheet_id to ewb_consolidated
-- ============================================================
-- Allows fetching all consolidated EWBs for a trip sheet
-- without joining through bilty or ewb_records.
-- ============================================================

ALTER TABLE ewb_consolidated
    ADD COLUMN IF NOT EXISTS trip_sheet_id UUID
        REFERENCES challan_trip_sheet(trip_sheet_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_ewb_consolidated_trip
    ON ewb_consolidated(trip_sheet_id) WHERE trip_sheet_id IS NOT NULL;

-- Backfill: fix existing rows where pdf_url is missing https://
UPDATE ewb_consolidated
SET pdf_url = 'https://' || pdf_url
WHERE pdf_url IS NOT NULL
  AND pdf_url NOT LIKE 'http%';
