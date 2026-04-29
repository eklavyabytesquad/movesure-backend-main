-- ============================================================
-- Migration 008: Challan Module
-- Run this on existing databases (already on schema 001-007).
-- Creates the 5 new challan objects, adds challan/kaat columns
-- to bilty, and adds kaat rate card to master_city_wise_transport.
-- ============================================================

-- ── challan_template ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS challan_template (
    template_id         UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID            NOT NULL REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id           UUID            NOT NULL REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,
    code                VARCHAR(50)     NOT NULL,
    name                VARCHAR(150)    NOT NULL,
    description         TEXT,
    slug                VARCHAR(100)    NOT NULL,
    template_type       VARCHAR(20)     NOT NULL DEFAULT 'CHALLAN'
                            CHECK (template_type IN ('CHALLAN', 'SUMMARY', 'KAAT_RECEIPT', 'LOADING_CHALLAN')),
    config              JSONB           NOT NULL DEFAULT '{}',
    is_default          BOOLEAN         NOT NULL DEFAULT FALSE,
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    CONSTRAINT uq_challan_template_code UNIQUE (company_id, branch_id, code),
    CONSTRAINT uq_challan_template_slug UNIQUE (company_id, branch_id, slug)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_challan_template_default
    ON challan_template(company_id, branch_id, template_type) WHERE is_default = TRUE;
CREATE INDEX IF NOT EXISTS idx_challan_template_company ON challan_template(company_id);
CREATE INDEX IF NOT EXISTS idx_challan_template_branch  ON challan_template(company_id, branch_id);
CREATE INDEX IF NOT EXISTS idx_challan_template_type    ON challan_template(company_id, branch_id, template_type);
CREATE INDEX IF NOT EXISTS idx_challan_template_active  ON challan_template(is_active) WHERE is_active = TRUE;
CREATE OR REPLACE TRIGGER trg_challan_template_updated_at
    BEFORE UPDATE ON challan_template
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── challan_book ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS challan_book (
    book_id             UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID            NOT NULL REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id           UUID            NOT NULL REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,
    book_name           VARCHAR(100),
    template_id         UUID            REFERENCES challan_template(template_id) ON DELETE SET NULL,
    route_scope         VARCHAR(12)     NOT NULL DEFAULT 'OPEN'
                            CHECK (route_scope IN ('FIXED_ROUTE', 'OPEN')),
    from_branch_id      UUID            REFERENCES tenant_branches(branch_id) ON DELETE SET NULL,
    to_branch_id        UUID            REFERENCES tenant_branches(branch_id) ON DELETE SET NULL,
    prefix              VARCHAR(20)     DEFAULT NULL,
    from_number         INTEGER         NOT NULL CHECK (from_number > 0),
    to_number           INTEGER         NOT NULL CHECK (to_number >= from_number),
    digits              INTEGER         NOT NULL DEFAULT 4 CHECK (digits BETWEEN 1 AND 10),
    postfix             VARCHAR(20)     DEFAULT NULL,
    current_number      INTEGER         NOT NULL,
    is_fixed            BOOLEAN         NOT NULL DEFAULT FALSE,
    auto_continue       BOOLEAN         NOT NULL DEFAULT FALSE,
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    is_completed        BOOLEAN         NOT NULL DEFAULT FALSE,
    is_primary          BOOLEAN         NOT NULL DEFAULT FALSE,
    metadata            JSONB           NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    CONSTRAINT chk_challan_book_current_number
        CHECK (current_number >= from_number AND current_number <= to_number + 1),
    CONSTRAINT chk_challan_book_route_scope CHECK (
        (route_scope = 'FIXED_ROUTE' AND from_branch_id IS NOT NULL AND to_branch_id IS NOT NULL)
        OR (route_scope = 'OPEN')
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_challan_book_primary
    ON challan_book(company_id, branch_id) WHERE is_primary = TRUE AND is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_challan_book_company    ON challan_book(company_id);
CREATE INDEX IF NOT EXISTS idx_challan_book_branch     ON challan_book(company_id, branch_id);
CREATE INDEX IF NOT EXISTS idx_challan_book_route      ON challan_book(from_branch_id, to_branch_id);
CREATE INDEX IF NOT EXISTS idx_challan_book_active     ON challan_book(company_id, branch_id, is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_challan_book_incomplete ON challan_book(company_id, branch_id, is_completed) WHERE is_completed = FALSE;
CREATE OR REPLACE TRIGGER trg_challan_book_updated_at
    BEFORE UPDATE ON challan_book
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── fn_next_challan_no ───────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_next_challan_no(p_book_id UUID)
RETURNS TABLE (challan_no TEXT, challan_number INTEGER)
LANGUAGE plpgsql AS $$
DECLARE
    v_current   INTEGER;
    v_to        INTEGER;
    v_prefix    VARCHAR;
    v_postfix   VARCHAR;
    v_digits    INTEGER;
    v_is_fixed  BOOLEAN;
BEGIN
    SELECT current_number, to_number, prefix, postfix, digits, is_fixed
    INTO   v_current, v_to, v_prefix, v_postfix, v_digits, v_is_fixed
    FROM   challan_book
    WHERE  book_id = p_book_id AND is_active = TRUE AND is_completed = FALSE
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'challan_book % is not available', p_book_id;
    END IF;
    IF v_current > v_to THEN
        UPDATE challan_book SET is_completed = TRUE WHERE book_id = p_book_id;
        RAISE EXCEPTION 'challan_book % is exhausted', p_book_id;
    END IF;
    IF NOT v_is_fixed THEN
        UPDATE challan_book
        SET current_number = current_number + 1,
            is_completed   = (current_number + 1 > v_to)
        WHERE book_id = p_book_id;
    END IF;

    RETURN QUERY
        SELECT COALESCE(v_prefix, '') || LPAD(v_current::TEXT, v_digits, '0') || COALESCE(v_postfix, ''),
               v_current;
END;
$$;

-- ── challan_trip_sheet ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS challan_trip_sheet (
    trip_sheet_id       UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID            NOT NULL REFERENCES tenant_companies(company_id) ON DELETE RESTRICT,
    trip_sheet_no       VARCHAR(50)     NOT NULL,
    transport_id        UUID            REFERENCES master_transport(transport_id) ON DELETE SET NULL,
    transport_name      VARCHAR(255),
    transport_gstin     VARCHAR(15),
    from_city_id        UUID            REFERENCES master_city(city_id) ON DELETE SET NULL,
    to_city_id          UUID            REFERENCES master_city(city_id) ON DELETE SET NULL,
    vehicle_info        JSONB           NOT NULL DEFAULT '{}',
    trip_date           DATE            NOT NULL DEFAULT CURRENT_DATE,
    status              VARCHAR(20)     NOT NULL DEFAULT 'DRAFT'
                            CHECK (status IN ('DRAFT', 'OPEN', 'DISPATCHED', 'ARRIVED', 'CLOSED')),
    is_dispatched       BOOLEAN         NOT NULL DEFAULT FALSE,
    dispatched_at       TIMESTAMPTZ,
    dispatched_by       UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    is_arrived          BOOLEAN         NOT NULL DEFAULT FALSE,
    arrived_at          TIMESTAMPTZ,
    arrived_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    total_challan_count INTEGER         NOT NULL DEFAULT 0 CHECK (total_challan_count >= 0),
    total_bilty_count   INTEGER         NOT NULL DEFAULT 0 CHECK (total_bilty_count >= 0),
    total_weight        NUMERIC         NOT NULL DEFAULT 0,
    total_packages      INTEGER         NOT NULL DEFAULT 0,
    total_freight       NUMERIC         NOT NULL DEFAULT 0,
    remarks             TEXT,
    pdf_url             TEXT,
    metadata            JSONB           NOT NULL DEFAULT '{}',
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    UNIQUE (company_id, trip_sheet_no)
);
CREATE INDEX IF NOT EXISTS idx_trip_sheet_company    ON challan_trip_sheet(company_id);
CREATE INDEX IF NOT EXISTS idx_trip_sheet_no         ON challan_trip_sheet(trip_sheet_no);
CREATE INDEX IF NOT EXISTS idx_trip_sheet_status     ON challan_trip_sheet(company_id, status);
CREATE INDEX IF NOT EXISTS idx_trip_sheet_date       ON challan_trip_sheet(trip_date DESC);
CREATE INDEX IF NOT EXISTS idx_trip_sheet_from_city  ON challan_trip_sheet(from_city_id);
CREATE INDEX IF NOT EXISTS idx_trip_sheet_to_city    ON challan_trip_sheet(to_city_id);
CREATE INDEX IF NOT EXISTS idx_trip_sheet_transport  ON challan_trip_sheet(transport_id);
CREATE INDEX IF NOT EXISTS idx_trip_sheet_dispatched ON challan_trip_sheet(company_id, dispatched_at) WHERE is_dispatched = TRUE;
CREATE INDEX IF NOT EXISTS idx_trip_sheet_active     ON challan_trip_sheet(company_id, is_active) WHERE is_active = TRUE;
CREATE OR REPLACE TRIGGER trg_challan_trip_sheet_updated_at
    BEFORE UPDATE ON challan_trip_sheet
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── challan ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS challan (
    challan_id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID            NOT NULL REFERENCES tenant_companies(company_id) ON DELETE RESTRICT,
    branch_id           UUID            NOT NULL REFERENCES tenant_branches(branch_id)   ON DELETE RESTRICT,
    challan_no          VARCHAR(50)     NOT NULL,
    book_id             UUID            REFERENCES challan_book(book_id) ON DELETE SET NULL,
    trip_sheet_id       UUID            REFERENCES challan_trip_sheet(trip_sheet_id) ON DELETE SET NULL,
    template_id         UUID            REFERENCES challan_template(template_id) ON DELETE SET NULL,
    from_branch_id      UUID            REFERENCES tenant_branches(branch_id) ON DELETE SET NULL,
    to_branch_id        UUID            REFERENCES tenant_branches(branch_id) ON DELETE SET NULL,
    transport_id        UUID            REFERENCES master_transport(transport_id) ON DELETE SET NULL,
    transport_name      VARCHAR(255),
    transport_gstin     VARCHAR(15),
    vehicle_info        JSONB           NOT NULL DEFAULT '{}',
    challan_date        DATE            NOT NULL DEFAULT CURRENT_DATE,
    total_bilty_count   INTEGER         NOT NULL DEFAULT 0 CHECK (total_bilty_count >= 0),
    status              VARCHAR(20)     NOT NULL DEFAULT 'DRAFT'
                            CHECK (status IN ('DRAFT', 'OPEN', 'DISPATCHED', 'ARRIVED_HUB', 'CLOSED')),
    is_dispatched       BOOLEAN         NOT NULL DEFAULT FALSE,
    dispatched_at       TIMESTAMPTZ,
    dispatched_by       UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    is_arrived_hub      BOOLEAN         NOT NULL DEFAULT FALSE,
    arrived_hub_at      TIMESTAMPTZ,
    arrived_hub_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    total_freight       NUMERIC         NOT NULL DEFAULT 0,
    total_weight        NUMERIC         NOT NULL DEFAULT 0,
    total_packages      INTEGER         NOT NULL DEFAULT 0,
    remarks             TEXT,
    pdf_url             TEXT,
    metadata            JSONB           NOT NULL DEFAULT '{}',
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    UNIQUE (company_id, branch_id, challan_no)
);
CREATE INDEX IF NOT EXISTS idx_challan_company        ON challan(company_id);
CREATE INDEX IF NOT EXISTS idx_challan_branch         ON challan(company_id, branch_id);
CREATE INDEX IF NOT EXISTS idx_challan_no             ON challan(challan_no);
CREATE INDEX IF NOT EXISTS idx_challan_status         ON challan(company_id, branch_id, status);
CREATE INDEX IF NOT EXISTS idx_challan_date           ON challan(challan_date DESC);
CREATE INDEX IF NOT EXISTS idx_challan_from_branch    ON challan(from_branch_id);
CREATE INDEX IF NOT EXISTS idx_challan_to_branch      ON challan(to_branch_id);
CREATE INDEX IF NOT EXISTS idx_challan_transport      ON challan(transport_id);
CREATE INDEX IF NOT EXISTS idx_challan_book           ON challan(book_id)           WHERE book_id       IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_challan_trip_sheet     ON challan(trip_sheet_id)     WHERE trip_sheet_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_challan_dispatched     ON challan(company_id, dispatched_at)  WHERE is_dispatched  = TRUE;
CREATE INDEX IF NOT EXISTS idx_challan_arrived_hub    ON challan(company_id, arrived_hub_at) WHERE is_arrived_hub = TRUE;
CREATE INDEX IF NOT EXISTS idx_challan_active         ON challan(company_id, branch_id, is_active) WHERE is_active = TRUE;
CREATE OR REPLACE TRIGGER trg_challan_updated_at
    BEFORE UPDATE ON challan
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── ALTER TABLE bilty ────────────────────────────────────────
ALTER TABLE bilty
    ADD COLUMN IF NOT EXISTS challan_id                  UUID REFERENCES challan(challan_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS challan_branch_id           UUID REFERENCES tenant_branches(branch_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS trip_sheet_id               UUID REFERENCES challan_trip_sheet(trip_sheet_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS challan_assigned_at         TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS challan_assigned_by         UUID REFERENCES iam_users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS kaat_rate                   NUMERIC     DEFAULT 0,
    ADD COLUMN IF NOT EXISTS kaat_rate_type              VARCHAR(10) DEFAULT NULL
        CHECK (kaat_rate_type IS NULL OR kaat_rate_type IN ('PER_KG', 'PER_PKG')),
    ADD COLUMN IF NOT EXISTS kaat_weight_charged         NUMERIC     DEFAULT 0,
    ADD COLUMN IF NOT EXISTS kaat_base_amount            NUMERIC     DEFAULT 0,
    ADD COLUMN IF NOT EXISTS kaat_receiving_slip_charge  NUMERIC     DEFAULT 0,
    ADD COLUMN IF NOT EXISTS kaat_bilty_charge           NUMERIC     DEFAULT 0,
    ADD COLUMN IF NOT EXISTS kaat_labour_rate            NUMERIC     DEFAULT 0,
    ADD COLUMN IF NOT EXISTS kaat_labour_rate_type       VARCHAR(10) DEFAULT NULL
        CHECK (kaat_labour_rate_type IS NULL OR kaat_labour_rate_type IN ('PER_KG', 'PER_PKG', 'PER_BILTY')),
    ADD COLUMN IF NOT EXISTS kaat_labour_charge          NUMERIC     DEFAULT 0,
    ADD COLUMN IF NOT EXISTS kaat_other_charges          JSONB       NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS kaat_other_charges_total    NUMERIC     DEFAULT 0,
    ADD COLUMN IF NOT EXISTS kaat_amount                 NUMERIC     DEFAULT 0,
    ADD COLUMN IF NOT EXISTS real_dd_charge              NUMERIC     DEFAULT 0,
    ADD COLUMN IF NOT EXISTS transit_profit              NUMERIC     DEFAULT 0,
    ADD COLUMN IF NOT EXISTS crossing_proof_type         VARCHAR(16) DEFAULT NULL
        CHECK (crossing_proof_type IS NULL OR crossing_proof_type IN ('POHONCH', 'CROSSING_BILTY')),
    ADD COLUMN IF NOT EXISTS crossing_proof_ref          VARCHAR(100) DEFAULT NULL;

-- crossing_proof CHECK (idempotent: drop then add)
ALTER TABLE bilty DROP CONSTRAINT IF EXISTS chk_bilty_crossing_proof;
ALTER TABLE bilty ADD CONSTRAINT chk_bilty_crossing_proof CHECK (
    (crossing_proof_type IS NULL AND crossing_proof_ref IS NULL)
    OR
    (crossing_proof_type IS NOT NULL AND crossing_proof_ref IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_bilty_challan_id          ON bilty(challan_id)          WHERE challan_id          IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_bilty_challan_branch      ON bilty(challan_branch_id)   WHERE challan_branch_id   IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_bilty_trip_sheet_id       ON bilty(trip_sheet_id)       WHERE trip_sheet_id       IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_bilty_crossing_proof_ref  ON bilty(crossing_proof_ref)  WHERE crossing_proof_ref  IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_bilty_crossing_proof_type ON bilty(company_id, branch_id, crossing_proof_type) WHERE crossing_proof_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_bilty_kaat_amount         ON bilty(company_id, branch_id, kaat_amount) WHERE kaat_amount > 0;
CREATE INDEX IF NOT EXISTS idx_bilty_transit_profit      ON bilty(company_id, branch_id, transit_profit);

-- ── ALTER TABLE master_city_wise_transport ────────────────────
ALTER TABLE master_city_wise_transport
    ADD COLUMN IF NOT EXISTS kaat_rate              NUMERIC     DEFAULT 0
        CHECK (kaat_rate IS NULL OR kaat_rate >= 0),
    ADD COLUMN IF NOT EXISTS kaat_rate_type         VARCHAR(10) NOT NULL DEFAULT 'PER_KG'
        CHECK (kaat_rate_type IN ('PER_KG', 'PER_PKG')),
    ADD COLUMN IF NOT EXISTS minimum_weight_kg      NUMERIC     DEFAULT 0
        CHECK (minimum_weight_kg IS NULL OR minimum_weight_kg >= 0),
    ADD COLUMN IF NOT EXISTS dd_charge_rate         NUMERIC     DEFAULT 0
        CHECK (dd_charge_rate IS NULL OR dd_charge_rate >= 0),
    ADD COLUMN IF NOT EXISTS dd_charge_rate_type    VARCHAR(10) NOT NULL DEFAULT 'FIXED'
        CHECK (dd_charge_rate_type IN ('FIXED', 'PER_KG', 'PER_PKG')),
    ADD COLUMN IF NOT EXISTS dd_minimum_charge      NUMERIC     DEFAULT 0
        CHECK (dd_minimum_charge IS NULL OR dd_minimum_charge >= 0),
    ADD COLUMN IF NOT EXISTS receiving_slip_charge  NUMERIC     DEFAULT 0
        CHECK (receiving_slip_charge IS NULL OR receiving_slip_charge >= 0),
    ADD COLUMN IF NOT EXISTS kaat_bilty_charge      NUMERIC     DEFAULT 0
        CHECK (kaat_bilty_charge IS NULL OR kaat_bilty_charge >= 0),
    ADD COLUMN IF NOT EXISTS kaat_labour_rate       NUMERIC     DEFAULT 0
        CHECK (kaat_labour_rate IS NULL OR kaat_labour_rate >= 0),
    ADD COLUMN IF NOT EXISTS kaat_labour_rate_type  VARCHAR(10) NOT NULL DEFAULT 'PER_KG'
        CHECK (kaat_labour_rate_type IN ('PER_KG', 'PER_PKG', 'PER_BILTY')),
    ADD COLUMN IF NOT EXISTS other_standard_charges JSONB       NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS content_types          JSONB       NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS kaat_effective_from    DATE        DEFAULT CURRENT_DATE,
    ADD COLUMN IF NOT EXISTS kaat_effective_to      DATE        DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_master_cwt_kaat_city         ON master_city_wise_transport(company_id, branch_id, city_id, kaat_rate_type) WHERE kaat_rate > 0;
CREATE INDEX IF NOT EXISTS idx_master_cwt_content_types     ON master_city_wise_transport USING GIN (content_types);
CREATE INDEX IF NOT EXISTS idx_master_cwt_other_std_charges ON master_city_wise_transport USING GIN (other_standard_charges);
