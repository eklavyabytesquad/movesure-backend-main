-- ============================================================
-- Migration 005 — Bilty new features
-- 1. bilty_template  — print template master (company + branch scoped)
-- 2. bilty_discount  — discount master with book-level scoping
-- 3. bilty_book      — add template_id FK
-- 4. bilty           — rename e_way_bill → e_way_bills (array),
--                      add actual_weight, template_id, local_charge,
--                      discount_id, discount_percentage, discount_amount
-- ============================================================


-- ── 1. bilty_template ────────────────────────────────────────────────────────

CREATE TABLE bilty_template (
    template_id     UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID            NOT NULL REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id       UUID            NOT NULL REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,
    code            VARCHAR(50)     NOT NULL,
    name            VARCHAR(150)    NOT NULL,
    description     TEXT,
    slug            VARCHAR(100)    NOT NULL,
    metadata        JSONB           NOT NULL DEFAULT '{}',
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    CONSTRAINT uq_bilty_template_code UNIQUE (company_id, branch_id, code),
    CONSTRAINT uq_bilty_template_slug UNIQUE (company_id, branch_id, slug)
);

CREATE INDEX idx_bilty_template_company ON bilty_template(company_id, branch_id);
CREATE INDEX idx_bilty_template_active  ON bilty_template(company_id, branch_id, is_active)
    WHERE is_active = TRUE;

CREATE TRIGGER trg_bilty_template_updated_at
    BEFORE UPDATE ON bilty_template
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ── 2. bilty_discount ────────────────────────────────────────────────────────

CREATE TABLE bilty_discount (
    discount_id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id            UUID        NOT NULL REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id             UUID        NOT NULL REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,
    discount_code         VARCHAR(50) NOT NULL,
    -- percentage applied to total_amount
    percentage            NUMERIC     NOT NULL DEFAULT 0 CHECK (percentage >= 0 AND percentage <= 100),
    -- optional: restrict this discount to bilties from a specific book
    bill_book_id          UUID        REFERENCES bilty_book(book_id) ON DELETE SET NULL,
    -- NULL = no cap
    max_amount_discounted NUMERIC     DEFAULT NULL CHECK (max_amount_discounted IS NULL OR max_amount_discounted >= 0),
    -- bilty total_amount must be >= this value to apply
    minimum_amount        NUMERIC     NOT NULL DEFAULT 0 CHECK (minimum_amount >= 0),
    is_active             BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by            UUID        REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by            UUID        REFERENCES iam_users(id) ON DELETE SET NULL,

    CONSTRAINT uq_bilty_discount_code UNIQUE (company_id, branch_id, discount_code)
);

CREATE INDEX idx_bilty_discount_company ON bilty_discount(company_id, branch_id);
CREATE INDEX idx_bilty_discount_book    ON bilty_discount(bill_book_id) WHERE bill_book_id IS NOT NULL;
CREATE INDEX idx_bilty_discount_active  ON bilty_discount(company_id, branch_id, is_active)
    WHERE is_active = TRUE;

CREATE TRIGGER trg_bilty_discount_updated_at
    BEFORE UPDATE ON bilty_discount
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ── 3. bilty_book — add template_id ──────────────────────────────────────────

ALTER TABLE bilty_book
    ADD COLUMN template_id UUID REFERENCES bilty_template(template_id) ON DELETE SET NULL;

CREATE INDEX idx_bilty_book_template ON bilty_book(template_id)
    WHERE template_id IS NOT NULL;


-- ── 4. bilty — multiple e-way bills, new columns ─────────────────────────────

-- Rename single e_way_bill object → e_way_bills array
-- Existing rows with empty object {} are migrated to empty array []
ALTER TABLE bilty RENAME COLUMN e_way_bill TO e_way_bills;
ALTER TABLE bilty ALTER COLUMN e_way_bills SET DEFAULT '[]';
UPDATE bilty SET e_way_bills = '[]' WHERE e_way_bills = '{}' OR e_way_bills = 'null' OR e_way_bills IS NULL;

-- Actual (physical) weight — distinct from billed weight
ALTER TABLE bilty ADD COLUMN actual_weight       NUMERIC;

-- Print template to use for this specific bilty (overrides book-level template)
ALTER TABLE bilty ADD COLUMN template_id         UUID REFERENCES bilty_template(template_id) ON DELETE SET NULL;

-- Additional charge: local delivery / handling
ALTER TABLE bilty ADD COLUMN local_charge        NUMERIC DEFAULT 0;

-- Discount columns
ALTER TABLE bilty ADD COLUMN discount_id         UUID REFERENCES bilty_discount(discount_id)  ON DELETE SET NULL;
ALTER TABLE bilty ADD COLUMN discount_percentage NUMERIC DEFAULT 0 CHECK (discount_percentage >= 0 AND discount_percentage <= 100);
ALTER TABLE bilty ADD COLUMN discount_amount     NUMERIC DEFAULT 0 CHECK (discount_amount >= 0);

-- Indexes
CREATE INDEX idx_bilty_template ON bilty(template_id) WHERE template_id IS NOT NULL;
CREATE INDEX idx_bilty_discount ON bilty(discount_id) WHERE discount_id IS NOT NULL;
