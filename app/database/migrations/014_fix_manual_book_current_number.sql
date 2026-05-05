-- Migration 014: Fix current_number for MANUAL bilty books
--
-- Convention (unified for both REGULAR and MANUAL):
--   current_number = NEXT number to issue
--
-- REGULAR: fn_next_gr_no(book_id) returns current_number, then increments it atomically.
-- MANUAL:  peek_gr_no reads current_number directly (no +1).
--          After save, advance_manual_book_counter sets current_number = used + 1.
--
-- Problem in existing data:
--   • Fresh MANUAL books: current_number = from_number ✓ (correct, peek shows from_number)
--   • MANUAL books with bilties already saved: current_number was set to used_number
--     (old buggy advance logic), but should be used_number + 1 (next to issue).
--
-- Example: RGT-MGLP — bilty 1401 created, current_number = 1401.
--   Peek would return 1401 again (already used). Should be 1402.
--
-- Fix: For MANUAL books that have at least one bilty, set
--   current_number = (highest gr_no number used) + 1
-- Books with no bilties are already correct (current_number = from_number).

UPDATE bilty_book bb
SET    current_number = (
           -- parse the numeric part of gr_no by stripping prefix/postfix,
           -- take the max, and add 1 so current_number = next to issue
           SELECT MAX(
               CAST(
                   REGEXP_REPLACE(
                       REGEXP_REPLACE(b.gr_no,
                           '^' || COALESCE(NULLIF(bb.prefix,  ''), ''), ''),
                       COALESCE(NULLIF(bb.postfix, ''), '') || '$', '')
                   AS INTEGER
               )
           ) + 1
           FROM bilty b
           WHERE b.book_id = bb.book_id
             AND b.is_active = true
       )
WHERE  bb.bilty_type = 'MANUAL'
  AND  bb.from_number IS NOT NULL
  AND  EXISTS (
           SELECT 1 FROM bilty b
           WHERE b.book_id = bb.book_id AND b.is_active = true
       );

-- Verify
-- SELECT book_id, book_name, from_number, to_number, current_number
-- FROM   bilty_book
-- WHERE  bilty_type = 'MANUAL'
-- ORDER  BY created_at;

