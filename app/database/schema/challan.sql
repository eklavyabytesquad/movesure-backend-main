-- ============================================================
-- CHALLAN MODULE — Full Schema
-- ============================================================
-- Tables: challan_template, challan_book, challan_trip_sheet, challan
-- Alters: bilty, master_city_wise_transport
--
-- Hub & Spoke:
--   Origin Branch → challan (truck) → Hub → onward transport (kaat)
--   → Destination / Door (real_dd_charge) → Consignee
--
-- kaat_amount = base + receiving_slip + bilty_chg + labour + other
-- transit_profit = total_amount − kaat_amount − real_dd_charge
--
-- Depends on: tenant.sql, iam.sql, bilty.sql, master.sql
-- ============================================================


-- ============================================================
-- challan_template
-- ============================================================
-- Print/field-visibility config per challan document type.
-- config JSONB: layout settings (orientation, columns, logo, etc.)
-- ============================================================
CREATE TABLE challan_template (
    template_id         UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Scope — every template belongs to a company + branch
    company_id          UUID            NOT NULL
                            REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id           UUID            NOT NULL
                            REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,

    -- Identity
    code                VARCHAR(50)     NOT NULL,   -- short machine key e.g. "CH-STD-A4"
    name                VARCHAR(150)    NOT NULL,   -- human label e.g. "Standard Challan A4"
    description         TEXT,
    slug                VARCHAR(100)    NOT NULL,   -- URL-friendly e.g. "challan-standard-a4"

    -- What this template renders
    template_type       VARCHAR(20)     NOT NULL DEFAULT 'CHALLAN'
                            CHECK (template_type IN (
                                'CHALLAN',          -- standard dispatch note
                                'SUMMARY',          -- loading manifest / summary sheet
                                'KAAT_RECEIPT',     -- kaat settlement receipt at hub
                                'LOADING_CHALLAN'   -- branch loading challan
                            )),

    -- Full layout/field config stored as JSONB — zero migration cost
    -- when adding new display options
    config              JSONB           NOT NULL DEFAULT '{}',

    -- Convenience flags
    is_default          BOOLEAN         NOT NULL DEFAULT FALSE,
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,

    -- Audit
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    -- Uniqueness within a branch
    CONSTRAINT uq_challan_template_code UNIQUE (company_id, branch_id, code),
    CONSTRAINT uq_challan_template_slug UNIQUE (company_id, branch_id, slug)
);

-- Only ONE default template per company + branch + template_type
CREATE UNIQUE INDEX uq_challan_template_default
    ON challan_template(company_id, branch_id, template_type)
    WHERE is_default = TRUE;

CREATE INDEX idx_challan_template_company ON challan_template(company_id);
CREATE INDEX idx_challan_template_branch  ON challan_template(company_id, branch_id);
CREATE INDEX idx_challan_template_type    ON challan_template(company_id, branch_id, template_type);
CREATE INDEX idx_challan_template_active  ON challan_template(is_active) WHERE is_active = TRUE;

CREATE TRIGGER trg_challan_template_updated_at
    BEFORE UPDATE ON challan_template
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- challan_book
-- ============================================================
-- Sequence book for challan numbers (mirrors bilty_book).
-- Formatted: prefix || LPAD(current_number, digits, '0') || postfix
-- route_scope: FIXED_ROUTE (one lane) | OPEN (all lanes)
-- is_primary: one default active book per company+branch
-- ============================================================
CREATE TABLE challan_book (
    book_id             UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Scope
    company_id          UUID            NOT NULL
                            REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id           UUID            NOT NULL
                            REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,

    -- Human label
    book_name           VARCHAR(100),                           -- e.g. "Challan Book FY25-26 Batch-A"

    -- Linked print template (used when printing challans from this book)
    template_id         UUID            REFERENCES challan_template(template_id) ON DELETE SET NULL,

    -- Route scope
    route_scope         VARCHAR(12)     NOT NULL DEFAULT 'OPEN'
                            CHECK (route_scope IN ('FIXED_ROUTE', 'OPEN')),

    -- Fixed-route endpoints — NULL when route_scope = 'OPEN'
    from_branch_id      UUID            REFERENCES tenant_branches(branch_id) ON DELETE SET NULL,
    to_branch_id        UUID            REFERENCES tenant_branches(branch_id) ON DELETE SET NULL,

    -- Number sequence
    prefix              VARCHAR(20)     DEFAULT NULL,           -- e.g. "CH/"
    from_number         INTEGER         NOT NULL CHECK (from_number > 0),
    to_number           INTEGER         NOT NULL CHECK (to_number >= from_number),
    digits              INTEGER         NOT NULL DEFAULT 4 CHECK (digits BETWEEN 1 AND 10),
    postfix             VARCHAR(20)     DEFAULT NULL,           -- e.g. "/25"
    current_number      INTEGER         NOT NULL,               -- next number to be issued

    -- Behaviour flags
    is_fixed            BOOLEAN         NOT NULL DEFAULT FALSE, -- TRUE = number never advances
    auto_continue       BOOLEAN         NOT NULL DEFAULT FALSE, -- TRUE = auto-create next book
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    is_completed        BOOLEAN         NOT NULL DEFAULT FALSE, -- TRUE = all numbers used
    is_primary          BOOLEAN         NOT NULL DEFAULT FALSE, -- one primary per company+branch

    metadata            JSONB           NOT NULL DEFAULT '{}',

    -- Audit
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    -- current_number must stay within [from_number, to_number + 1]
    -- (to_number + 1 is the exhausted sentinel value)
    CONSTRAINT chk_challan_book_current_number
        CHECK (current_number >= from_number AND current_number <= to_number + 1),

    -- FIXED_ROUTE requires both branch FKs; OPEN requires neither
    CONSTRAINT chk_challan_book_route_scope CHECK (
        (route_scope = 'FIXED_ROUTE'
            AND from_branch_id IS NOT NULL
            AND to_branch_id   IS NOT NULL)
        OR
        (route_scope = 'OPEN')
    )
);

-- Exactly one primary book per company + branch (when active)
CREATE UNIQUE INDEX uq_challan_book_primary
    ON challan_book(company_id, branch_id)
    WHERE is_primary = TRUE AND is_active = TRUE;

CREATE INDEX idx_challan_book_company    ON challan_book(company_id);
CREATE INDEX idx_challan_book_branch     ON challan_book(company_id, branch_id);
CREATE INDEX idx_challan_book_route      ON challan_book(from_branch_id, to_branch_id);
CREATE INDEX idx_challan_book_active     ON challan_book(company_id, branch_id, is_active)
    WHERE is_active = TRUE;
CREATE INDEX idx_challan_book_incomplete ON challan_book(company_id, branch_id, is_completed)
    WHERE is_completed = FALSE;

CREATE TRIGGER trg_challan_book_updated_at
    BEFORE UPDATE ON challan_book
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- fn_next_challan_no(p_book_id)
-- ============================================================
-- Atomically issues the next challan number (FOR UPDATE lock).
-- Returns (challan_no TEXT, challan_number INTEGER).
-- Call inside the same transaction as the challan INSERT.
-- ============================================================
CREATE OR REPLACE FUNCTION fn_next_challan_no(p_book_id UUID)
RETURNS TABLE (challan_no TEXT, challan_number INTEGER)
LANGUAGE plpgsql
AS $$
DECLARE
    v_current   INTEGER;
    v_to        INTEGER;
    v_prefix    VARCHAR;
    v_postfix   VARCHAR;
    v_digits    INTEGER;
    v_is_fixed  BOOLEAN;
BEGIN
    -- Lock row to prevent concurrent duplicate number issuance
    SELECT current_number, to_number, prefix, postfix, digits, is_fixed
    INTO   v_current, v_to, v_prefix, v_postfix, v_digits, v_is_fixed
    FROM   challan_book
    WHERE  book_id      = p_book_id
      AND  is_active    = TRUE
      AND  is_completed = FALSE
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'challan_book % is not available (missing, inactive, or completed)',
            p_book_id;
    END IF;

    IF v_current > v_to THEN
        -- Mark exhausted and abort — caller must handle this
        UPDATE challan_book SET is_completed = TRUE WHERE book_id = p_book_id;
        RAISE EXCEPTION
            'challan_book % is exhausted — all numbers in the range have been used',
            p_book_id;
    END IF;

    -- Advance counter unless in fixed mode
    IF NOT v_is_fixed THEN
        UPDATE challan_book
           SET current_number = current_number + 1,
               is_completed   = (current_number + 1 > v_to)
         WHERE book_id = p_book_id;
    END IF;

    -- Return formatted challan string + raw integer
    RETURN QUERY SELECT
        COALESCE(v_prefix, '') || LPAD(v_current::TEXT, v_digits, '0') || COALESCE(v_postfix, ''),
        v_current;
END;
$$;


-- ============================================================
-- challan_trip_sheet
-- ============================================================
-- Company-level truck trip record (NOT branch-scoped).
-- One physical truck + one journey. Multiple branches load their
-- challans onto one trip sheet. Cross-branch allowed by design.
-- status: DRAFT → OPEN → DISPATCHED → ARRIVED → CLOSED
-- vehicle_info JSONB: {truck_no, owner_name, driver_name, driver_mobile, truck_type}
-- ============================================================
CREATE TABLE challan_trip_sheet (
    trip_sheet_id           UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Company-scoped — spans multiple branches
    company_id              UUID            NOT NULL
                                REFERENCES tenant_companies(company_id) ON DELETE RESTRICT,

    trip_sheet_no           VARCHAR(50)     NOT NULL,

    -- Transport operator for this truck trip
    transport_id            UUID            REFERENCES master_transport(transport_id) ON DELETE SET NULL,
    transport_name          VARCHAR(255),
    transport_gstin         VARCHAR(15),

    -- Overall journey endpoints (truck route)
    from_city_id            UUID            REFERENCES master_city(city_id) ON DELETE SET NULL,
    to_city_id              UUID            REFERENCES master_city(city_id) ON DELETE SET NULL,

    -- Vehicle + crew details snapshotted at creation / dispatch
    vehicle_info            JSONB           NOT NULL DEFAULT '{}',

    -- ── Fleet FKs (from fleet.sql — loaded before this file) ────
    -- Link to the fleet record for this truck. driver_id / owner_id /
    -- conductor_id point to fleet_staff rows.
    -- vehicle_info is retained as a dispatch-time snapshot.
    fleet_id                UUID            REFERENCES fleet(fleet_id)       ON DELETE SET NULL,
    driver_id               UUID            REFERENCES fleet_staff(staff_id) ON DELETE SET NULL,
    owner_id                UUID            REFERENCES fleet_staff(staff_id) ON DELETE SET NULL,
    conductor_id            UUID            REFERENCES fleet_staff(staff_id) ON DELETE SET NULL,

    trip_date               DATE            NOT NULL DEFAULT CURRENT_DATE,

    -- ── Status / lifecycle ──────────────────────────────────
    status                  VARCHAR(20)     NOT NULL DEFAULT 'DRAFT'
                                CHECK (status IN (
                                    'DRAFT',       -- building; challans can be added
                                    'OPEN',        -- finalised; truck confirmed
                                    'DISPATCHED',  -- truck physically left
                                    'ARRIVED',     -- truck reached destination
                                    'CLOSED'       -- fully reconciled
                                )),

    -- ── Dispatch event ──────────────────────────────────────
    is_dispatched           BOOLEAN         NOT NULL DEFAULT FALSE,
    dispatched_at           TIMESTAMPTZ,
    dispatched_by           UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    -- ── Arrival event ───────────────────────────────────────
    is_arrived              BOOLEAN         NOT NULL DEFAULT FALSE,
    arrived_at              TIMESTAMPTZ,
    arrived_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    -- ── Aggregates across ALL attached challans ──────────────
    -- App layer keeps these in sync when challans are added/removed.
    total_challan_count     INTEGER         NOT NULL DEFAULT 0 CHECK (total_challan_count >= 0),
    total_bilty_count       INTEGER         NOT NULL DEFAULT 0 CHECK (total_bilty_count >= 0),
    total_weight            NUMERIC         NOT NULL DEFAULT 0,
    total_packages          INTEGER         NOT NULL DEFAULT 0,
    total_freight           NUMERIC         NOT NULL DEFAULT 0,

    remarks                 TEXT,
    pdf_url                 TEXT,           -- consolidated trip sheet PDF
    metadata                JSONB           NOT NULL DEFAULT '{}',

    is_active               BOOLEAN         NOT NULL DEFAULT TRUE,

    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    UNIQUE (company_id, trip_sheet_no)
);

CREATE INDEX idx_trip_sheet_company    ON challan_trip_sheet(company_id);
CREATE INDEX idx_trip_sheet_no         ON challan_trip_sheet(trip_sheet_no);
CREATE INDEX idx_trip_sheet_status     ON challan_trip_sheet(company_id, status);
CREATE INDEX idx_trip_sheet_date       ON challan_trip_sheet(trip_date DESC);
CREATE INDEX idx_trip_sheet_from_city  ON challan_trip_sheet(from_city_id);
CREATE INDEX idx_trip_sheet_to_city    ON challan_trip_sheet(to_city_id);
CREATE INDEX idx_trip_sheet_transport  ON challan_trip_sheet(transport_id);
CREATE INDEX idx_trip_sheet_dispatched ON challan_trip_sheet(company_id, dispatched_at)
    WHERE is_dispatched = TRUE;
CREATE INDEX idx_trip_sheet_active     ON challan_trip_sheet(company_id, is_active)
    WHERE is_active = TRUE;

CREATE TRIGGER trg_challan_trip_sheet_updated_at
    BEFORE UPDATE ON challan_trip_sheet
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- challan
-- ============================================================
-- Branch-level dispatch record. One challan = N bilties from one
-- branch on one truck. Links up to a challan_trip_sheet (optional).
-- status: DRAFT → OPEN → DISPATCHED → ARRIVED_HUB → CLOSED
-- ============================================================
CREATE TABLE challan (
    challan_id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Scope — every challan belongs to a company + branch
    company_id          UUID            NOT NULL
                            REFERENCES tenant_companies(company_id) ON DELETE RESTRICT,
    branch_id           UUID            NOT NULL
                            REFERENCES tenant_branches(branch_id)   ON DELETE RESTRICT,

    -- Number (issued from a challan_book via fn_next_challan_no)
    challan_no          VARCHAR(50)     NOT NULL,
    book_id             UUID            REFERENCES challan_book(book_id) ON DELETE SET NULL,

    -- Link to trip sheet when multiple branches share one truck.
    -- NULL = standalone single-branch challan (most common).
    trip_sheet_id       UUID            REFERENCES challan_trip_sheet(trip_sheet_id) ON DELETE SET NULL,

    -- Print template override (falls back to challan_book.template_id)
    template_id         UUID            REFERENCES challan_template(template_id) ON DELETE SET NULL,

    -- Route — origin and destination branches
    -- NULL is allowed for ad-hoc / single-branch challans
    from_branch_id      UUID            REFERENCES tenant_branches(branch_id) ON DELETE SET NULL,
    to_branch_id        UUID            REFERENCES tenant_branches(branch_id) ON DELETE SET NULL,

    -- Which transport company is physically carrying this challan
    transport_id        UUID            REFERENCES master_transport(transport_id) ON DELETE SET NULL,

    transport_name      VARCHAR(255),
    transport_gstin     VARCHAR(15),
    vehicle_info        JSONB           NOT NULL DEFAULT '{}',

    -- ── Fleet FKs (from fleet.sql — loaded before this file) ────
    fleet_id            UUID            REFERENCES fleet(fleet_id)       ON DELETE SET NULL,
    driver_id           UUID            REFERENCES fleet_staff(staff_id) ON DELETE SET NULL,
    owner_id            UUID            REFERENCES fleet_staff(staff_id) ON DELETE SET NULL,
    conductor_id        UUID            REFERENCES fleet_staff(staff_id) ON DELETE SET NULL,

    challan_date        DATE            NOT NULL DEFAULT CURRENT_DATE,
    total_bilty_count   INTEGER         NOT NULL DEFAULT 0 CHECK (total_bilty_count >= 0),

    status              VARCHAR(20)     NOT NULL DEFAULT 'DRAFT'
                            CHECK (status IN (
                                'DRAFT',        -- being built; bilties editable
                                'OPEN',         -- locked and ready to dispatch
                                'DISPATCHED',   -- truck left origin branch
                                'ARRIVED_HUB',  -- reached hub / destination
                                'CLOSED'        -- reconciled; kaat settled
                            )),

    is_dispatched       BOOLEAN         NOT NULL DEFAULT FALSE,
    dispatched_at       TIMESTAMPTZ,
    dispatched_by       UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    is_arrived_hub      BOOLEAN         NOT NULL DEFAULT FALSE,
    arrived_hub_at      TIMESTAMPTZ,
    arrived_hub_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    -- App layer keeps these in sync when bilties are added/removed
    total_freight       NUMERIC         NOT NULL DEFAULT 0,
    total_weight        NUMERIC         NOT NULL DEFAULT 0,
    total_packages      INTEGER         NOT NULL DEFAULT 0,

    remarks             TEXT,
    pdf_url             TEXT,
    metadata            JSONB           NOT NULL DEFAULT '{}',
    is_primary          BOOLEAN         NOT NULL DEFAULT FALSE,
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,

    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    -- Challan number must be unique within a company + branch
    UNIQUE (company_id, branch_id, challan_no)
);

-- ── Challan indexes ──────────────────────────────────────────
CREATE INDEX idx_challan_company        ON challan(company_id);
CREATE INDEX idx_challan_branch         ON challan(company_id, branch_id);
CREATE INDEX idx_challan_no             ON challan(challan_no);
CREATE INDEX idx_challan_status         ON challan(company_id, branch_id, status);
CREATE UNIQUE INDEX uq_challan_primary  ON challan(company_id, branch_id)
    WHERE is_primary = TRUE AND is_active = TRUE AND status NOT IN ('DISPATCHED','ARRIVED_HUB','CLOSED');
CREATE INDEX idx_challan_date           ON challan(challan_date DESC);
CREATE INDEX idx_challan_from_branch    ON challan(from_branch_id);
CREATE INDEX idx_challan_to_branch      ON challan(to_branch_id);
CREATE INDEX idx_challan_transport      ON challan(transport_id);
CREATE INDEX idx_challan_book           ON challan(book_id) WHERE book_id IS NOT NULL;
CREATE INDEX idx_challan_trip_sheet     ON challan(trip_sheet_id) WHERE trip_sheet_id IS NOT NULL;

-- Partial indexes for active lifecycle queries
CREATE INDEX idx_challan_dispatched     ON challan(company_id, dispatched_at)
    WHERE is_dispatched = TRUE;
CREATE INDEX idx_challan_arrived_hub    ON challan(company_id, arrived_hub_at)
    WHERE is_arrived_hub = TRUE;
CREATE INDEX idx_challan_active         ON challan(company_id, branch_id, is_active)
    WHERE is_active = TRUE;

CREATE TRIGGER trg_challan_updated_at
    BEFORE UPDATE ON challan
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- FK back-references from bilty → challan tables
-- bilty.challan_id and bilty.trip_sheet_id are plain UUID columns
-- in bilty.sql (no FK there — forward reference).
-- FK constraints are wired here after both tables exist.
-- ============================================================
ALTER TABLE bilty
    ADD CONSTRAINT fk_bilty_challan
        FOREIGN KEY (challan_id) REFERENCES challan(challan_id) ON DELETE SET NULL,
    ADD CONSTRAINT fk_bilty_trip_sheet
        FOREIGN KEY (trip_sheet_id) REFERENCES challan_trip_sheet(trip_sheet_id) ON DELETE SET NULL;

CREATE INDEX idx_bilty_challan_id    ON bilty(challan_id)    WHERE challan_id    IS NOT NULL;
CREATE INDEX idx_bilty_trip_sheet_id ON bilty(trip_sheet_id) WHERE trip_sheet_id IS NOT NULL;


-- ============================================================
-- Fleet FK indexes on challan and challan_trip_sheet
-- ============================================================
CREATE INDEX idx_challan_fleet          ON challan(fleet_id)     WHERE fleet_id     IS NOT NULL;
CREATE INDEX idx_challan_driver         ON challan(driver_id)    WHERE driver_id    IS NOT NULL;
CREATE INDEX idx_challan_owner          ON challan(owner_id)     WHERE owner_id     IS NOT NULL;
CREATE INDEX idx_challan_conductor      ON challan(conductor_id) WHERE conductor_id IS NOT NULL;

CREATE INDEX idx_trip_sheet_fleet       ON challan_trip_sheet(fleet_id)     WHERE fleet_id     IS NOT NULL;
CREATE INDEX idx_trip_sheet_driver      ON challan_trip_sheet(driver_id)    WHERE driver_id    IS NOT NULL;
CREATE INDEX idx_trip_sheet_owner       ON challan_trip_sheet(owner_id)     WHERE owner_id     IS NOT NULL;
CREATE INDEX idx_trip_sheet_conductor   ON challan_trip_sheet(conductor_id) WHERE conductor_id IS NOT NULL;

