-- ============================================================
-- Migration 006 — Primary bilty book and primary template
--
-- Adds is_primary flag to bilty_book and bilty_template.
-- Only one row per (company_id, branch_id, bilty_type) can be
-- primary for books; only one per (company_id, branch_id) for
-- templates.
-- Partial unique index enforces this at the DB level.
-- ============================================================


-- ── bilty_book ───────────────────────────────────────────────
ALTER TABLE bilty_book
    ADD COLUMN is_primary BOOLEAN NOT NULL DEFAULT FALSE;

-- One primary REGULAR book and one primary MANUAL book per branch
CREATE UNIQUE INDEX uq_bilty_book_primary
    ON bilty_book(company_id, branch_id, bilty_type)
    WHERE is_primary = TRUE;


-- ── bilty_template ───────────────────────────────────────────
ALTER TABLE bilty_template
    ADD COLUMN is_primary BOOLEAN NOT NULL DEFAULT FALSE;

-- One primary template per branch
CREATE UNIQUE INDEX uq_bilty_template_primary
    ON bilty_template(company_id, branch_id)
    WHERE is_primary = TRUE;
