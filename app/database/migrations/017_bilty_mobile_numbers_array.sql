-- ============================================================
-- Migration: Add mobile_numbers JSONB array fields to bilty
-- ============================================================
-- Adds support for multiple mobile numbers in bilty snapshots
-- Stores array of phone numbers for consignor, consignee, transport
-- ============================================================

-- Add mobile_numbers columns to bilty table
ALTER TABLE bilty
ADD COLUMN consignor_mobile_numbers JSONB DEFAULT '[]'::jsonb;

ALTER TABLE bilty
ADD COLUMN consignee_mobile_numbers JSONB DEFAULT '[]'::jsonb;

ALTER TABLE bilty
ADD COLUMN transport_mobile_numbers JSONB DEFAULT '[]'::jsonb;

-- Create indexes for better query performance
CREATE INDEX idx_bilty_consignor_mobile_numbers ON bilty
  USING GIN (consignor_mobile_numbers);

CREATE INDEX idx_bilty_consignee_mobile_numbers ON bilty
  USING GIN (consignee_mobile_numbers);

CREATE INDEX idx_bilty_transport_mobile_numbers ON bilty
  USING GIN (transport_mobile_numbers);
