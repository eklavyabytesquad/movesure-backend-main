-- ============================================================
-- Migration 007 — template_type on bilty_template
--                  book_defaults JSONB on bilty_book
--
-- 1. bilty_template — adds template_type (what the template is
--    used for) and an optional book_id FK (pin template to a
--    specific bilty book instead of being branch-wide).
--
-- 2. bilty_book — adds book_defaults JSONB that stores
--    pre-filled form values (delivery_type, payment_mode,
--    from_city_id, etc.) so the frontend can pre-populate the
--    create-bilty form without user re-entry.
-- ============================================================


-- ── 1. bilty_template — template_type ────────────────────────────────────────

ALTER TABLE bilty_template
    ADD COLUMN template_type  VARCHAR(30) NOT NULL DEFAULT 'REGULAR_BILTY'
        CONSTRAINT chk_bilty_template_type CHECK (
            template_type IN (
                'REGULAR_BILTY',        -- used when printing a regular (book-based) bilty
                'MANUAL_BILTY',         -- used when printing a manual / station bilty
                'MONTHLY_CONSIGNOR',    -- monthly consignment bill sent to consignor
                'MONTHLY_CONSIGNEE'     -- monthly consignment bill sent to consignee
            )
        );

-- Optional: pin a template to a specific bilty book.
-- NULL means the template is available to the entire branch.
ALTER TABLE bilty_template
    ADD COLUMN book_id  UUID  REFERENCES bilty_book(book_id) ON DELETE SET NULL;

CREATE INDEX idx_bilty_template_type ON bilty_template(company_id, branch_id, template_type);
CREATE INDEX idx_bilty_template_book ON bilty_template(book_id) WHERE book_id IS NOT NULL;


-- ── 2. bilty_book — book_defaults ────────────────────────────────────────────

-- book_defaults stores form pre-fill values for the create-bilty screen.
-- All keys are optional — only the ones you want to pre-fill need to be set.
--
-- Supported keys:
--   delivery_type   VARCHAR  e.g. "GODOWN" | "DOOR"
--   payment_mode    VARCHAR  e.g. "TO-PAY" | "PAID" | "FOC"
--   from_city_id    UUID     e.g. "0fb3a1fd-933b-46fa-b7d8-1bab7a99e43d"
--   to_city_id      UUID     optional default destination city
--   transport_id    UUID     optional default transport
--
-- Example:
--   {
--     "delivery_type": "GODOWN",
--     "payment_mode":  "TO-PAY",
--     "from_city_id":  "0fb3a1fd-933b-46fa-b7d8-1bab7a99e43d"
--   }

ALTER TABLE bilty_book
    ADD COLUMN book_defaults  JSONB  NOT NULL DEFAULT '{}';
