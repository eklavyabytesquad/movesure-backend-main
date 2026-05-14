-- ============================================================
-- Migration: Add mobile_numbers JSONB array field
-- ============================================================
-- Adds support for multiple mobile numbers in consignor and consignee
-- Stores array of phone numbers, e.g.: ["1234123415", "1231132415"]
-- ============================================================

-- Add mobile_numbers column to bilty_consignor
ALTER TABLE bilty_consignor
ADD COLUMN mobile_numbers JSONB DEFAULT '[]'::jsonb;

-- Add mobile_numbers column to bilty_consignee
ALTER TABLE bilty_consignee
ADD COLUMN mobile_numbers JSONB DEFAULT '[]'::jsonb;

-- Create index for better query performance
CREATE INDEX idx_bilty_consignor_mobile_numbers ON bilty_consignor
  USING GIN (mobile_numbers);

CREATE INDEX idx_bilty_consignee_mobile_numbers ON bilty_consignee
  USING GIN (mobile_numbers);
