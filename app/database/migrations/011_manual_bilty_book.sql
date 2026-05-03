-- ============================================================
-- Migration 011: Manual Bilty Book Support
--
-- MANUAL bilty books hold only book_defaults (pre-fill values
-- like from_city_id) — they have no GR number series.
-- The from_number / to_number / current_number columns are
-- meaningless for MANUAL books and must be nullable.
--
-- Changes:
--   1. Drop NOT NULL from bilty_book.from_number
--   2. Drop NOT NULL from bilty_book.to_number
--   3. Drop NOT NULL from bilty_book.current_number
--   4. Drop old chk_bilty_book_current_number constraint
--      (it assumed all three columns are always non-null)
--   5. Add new constraint that:
--        - MANUAL books: skips all number checks
--        - REGULAR books: enforces original range logic
--
-- Safe to re-run: uses IF EXISTS / conditional drops.
-- ============================================================

-- 1. Make series columns nullable
ALTER TABLE bilty_book
    ALTER COLUMN from_number    DROP NOT NULL,
    ALTER COLUMN to_number      DROP NOT NULL,
    ALTER COLUMN current_number DROP NOT NULL;

-- 2. Drop the old range constraint (enforced NOT NULL logic)
ALTER TABLE bilty_book
    DROP CONSTRAINT IF EXISTS chk_bilty_book_current_number;

-- 3. Add new constraint:
--    MANUAL books  → skip number checks entirely (NULLs allowed)
--    REGULAR books → enforce original logic
ALTER TABLE bilty_book
    ADD CONSTRAINT chk_bilty_book_current_number CHECK (
        bilty_type = 'MANUAL'
        OR (
            current_number IS NOT NULL
            AND from_number    IS NOT NULL
            AND to_number      IS NOT NULL
            AND current_number >= from_number
            AND current_number <= to_number + 1
        )
    );
