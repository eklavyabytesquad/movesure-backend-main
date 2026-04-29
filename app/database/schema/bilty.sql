-- ============================================================
-- BILTY MODULE TABLES
--
--   bilty_consignor      → Consignor (shipper) master
--   bilty_consignee      → Consignee (receiver) master
--   bilty_book           → GR/LR number books (per company + branch)
--   fn_next_gr_no()      → Atomic GR number generation (no reservation table)
--   bilty_rate           → Consignor OR consignee + destination-city rate profile
--   bilty_template       → Print template master (company + branch scoped)
--   bilty_discount       → Discount master (company + branch scoped)
--   bilty                → Unified bilty (REGULAR + MANUAL) with full
--                          lifecycle tracking columns
--
-- Depends on:
--   tenant.sql  → tenant_companies, tenant_branches
--   iam.sql     → iam_users
--   master.sql  → master_city, master_transport
-- ============================================================


-- ============================================================
-- bilty_consignor
-- Shipper / sender master, company + branch scoped.
-- The bilty row snapshots name/gstin/mobile at creation time
-- so historical records stay accurate after master edits.
-- ============================================================
CREATE TABLE bilty_consignor (
    consignor_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID            NOT NULL REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id           UUID            NOT NULL REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,
    consignor_name      VARCHAR(255)    NOT NULL,
    gstin               VARCHAR(15),
    pan                 VARCHAR(10),
    aadhar              VARCHAR(12),
    address             TEXT,
    city                VARCHAR(150),
    state               VARCHAR(100),
    pincode             VARCHAR(10),
    mobile              VARCHAR(15),
    alternate_mobile    VARCHAR(15),
    email               VARCHAR(255),
    outstanding_amount  NUMERIC         NOT NULL DEFAULT 0,
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    metadata            JSONB           NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL
);

CREATE INDEX idx_bilty_consignor_company    ON bilty_consignor(company_id);
CREATE INDEX idx_bilty_consignor_branch     ON bilty_consignor(company_id, branch_id);
CREATE INDEX idx_bilty_consignor_gstin      ON bilty_consignor(gstin);
CREATE INDEX idx_bilty_consignor_mobile     ON bilty_consignor(mobile);
CREATE INDEX idx_bilty_consignor_active     ON bilty_consignor(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_bilty_consignor_name_fts   ON bilty_consignor
    USING GIN (to_tsvector('simple', consignor_name));

CREATE TRIGGER trg_bilty_consignor_updated_at
    BEFORE UPDATE ON bilty_consignor
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- bilty_consignee
-- Receiver / destination party master, company + branch scoped.
-- ============================================================
CREATE TABLE bilty_consignee (
    consignee_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID            NOT NULL REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id           UUID            NOT NULL REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,
    consignee_name      VARCHAR(255)    NOT NULL,
    gstin               VARCHAR(15),
    pan                 VARCHAR(10),
    aadhar              VARCHAR(12),
    address             TEXT,
    city                VARCHAR(150),
    state               VARCHAR(100),
    pincode             VARCHAR(10),
    mobile              VARCHAR(15),
    alternate_mobile    VARCHAR(15),
    email               VARCHAR(255),
    outstanding_amount  NUMERIC         NOT NULL DEFAULT 0,
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    metadata            JSONB           NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL
);

CREATE INDEX idx_bilty_consignee_company    ON bilty_consignee(company_id);
CREATE INDEX idx_bilty_consignee_branch     ON bilty_consignee(company_id, branch_id);
CREATE INDEX idx_bilty_consignee_gstin      ON bilty_consignee(gstin);
CREATE INDEX idx_bilty_consignee_mobile     ON bilty_consignee(mobile);
CREATE INDEX idx_bilty_consignee_active     ON bilty_consignee(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_bilty_consignee_name_fts   ON bilty_consignee
    USING GIN (to_tsvector('simple', consignee_name));

CREATE TRIGGER trg_bilty_consignee_updated_at
    BEFORE UPDATE ON bilty_consignee
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- bilty_book
-- Holds the GR/LR number range for a company + branch.
-- Generated GR = prefix || LPAD(current_number, digits, '0') || postfix
--
-- bilty_type    : REGULAR (from book sequence) | MANUAL (station bilty)
-- party_scope   : COMMON  → any user can consume numbers from this book
--                 CONSIGNOR → book is locked to a specific consignor
--                 CONSIGNEE → book is locked to a specific consignee
--                 consignor_id / consignee_id must match party_scope
--                 (enforced by chk_bilty_book_party_scope)
-- is_fixed      : if TRUE the current_number does not auto-increment
-- auto_continue : if TRUE, mark completed & create next book when
--                 range is exhausted (app-layer logic)
-- is_completed  : set TRUE when current_number > to_number
-- ============================================================
CREATE TABLE bilty_book (
    book_id         UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID            NOT NULL REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id       UUID            NOT NULL REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,
    book_name       VARCHAR(100),                           -- human label e.g. "Book-A 2025-26"
    template_name   VARCHAR(100),                           -- optional print template e.g. "A4-Standard"
    template_id     UUID            REFERENCES bilty_template(template_id) ON DELETE SET NULL,

    -- Which bilty type this book issues GRs for
    bilty_type      VARCHAR(10)     NOT NULL DEFAULT 'REGULAR'
                        CHECK (bilty_type IN ('REGULAR', 'MANUAL')),

    -- Who this book belongs to
    party_scope     VARCHAR(10)     NOT NULL DEFAULT 'COMMON'
                        CHECK (party_scope IN ('COMMON', 'CONSIGNOR', 'CONSIGNEE')),
    consignor_id    UUID            REFERENCES bilty_consignor(consignor_id) ON DELETE SET NULL,
    consignee_id    UUID            REFERENCES bilty_consignee(consignee_id) ON DELETE SET NULL,

    prefix          VARCHAR(20)     DEFAULT NULL,
    from_number     INTEGER         NOT NULL CHECK (from_number > 0),
    to_number       INTEGER         NOT NULL CHECK (to_number >= from_number),
    digits          INTEGER         NOT NULL DEFAULT 4 CHECK (digits BETWEEN 1 AND 10),
    postfix         VARCHAR(20)     DEFAULT NULL,
    current_number  INTEGER         NOT NULL,               -- next number to be issued
    is_fixed        BOOLEAN         NOT NULL DEFAULT FALSE,
    auto_continue   BOOLEAN         NOT NULL DEFAULT FALSE,
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    is_completed    BOOLEAN         NOT NULL DEFAULT FALSE,
    is_primary      BOOLEAN         NOT NULL DEFAULT FALSE,  -- one primary per (company, branch, bilty_type)
    metadata        JSONB           NOT NULL DEFAULT '{}',
    book_defaults   JSONB           NOT NULL DEFAULT '{}',  -- pre-fill values for the create-bilty form
    --   keys: delivery_type, payment_mode, from_city_id, to_city_id, transport_id
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    CONSTRAINT chk_bilty_book_current_number
        CHECK (current_number >= from_number AND current_number <= to_number + 1),

    -- COMMON  : both party FKs must be NULL
    -- CONSIGNOR: consignor_id set, consignee_id NULL
    -- CONSIGNEE: consignee_id set, consignor_id NULL
    CONSTRAINT chk_bilty_book_party_scope CHECK (
        (party_scope = 'COMMON'    AND consignor_id IS NULL AND consignee_id IS NULL)
        OR
        (party_scope = 'CONSIGNOR' AND consignor_id IS NOT NULL AND consignee_id IS NULL)
        OR
        (party_scope = 'CONSIGNEE' AND consignee_id IS NOT NULL AND consignor_id IS NULL)
    )
);

CREATE INDEX idx_bilty_book_company     ON bilty_book(company_id);
CREATE INDEX idx_bilty_book_branch      ON bilty_book(company_id, branch_id);
CREATE INDEX idx_bilty_book_bilty_type  ON bilty_book(company_id, branch_id, bilty_type);
CREATE INDEX idx_bilty_book_scope       ON bilty_book(company_id, branch_id, party_scope);
CREATE INDEX idx_bilty_book_consignor   ON bilty_book(consignor_id) WHERE consignor_id IS NOT NULL;
CREATE INDEX idx_bilty_book_consignee   ON bilty_book(consignee_id) WHERE consignee_id IS NOT NULL;
CREATE INDEX idx_bilty_book_active      ON bilty_book(company_id, branch_id, is_active)
    WHERE is_active = TRUE;
CREATE INDEX idx_bilty_book_incomplete  ON bilty_book(company_id, branch_id, is_completed)
    WHERE is_completed = FALSE;
CREATE UNIQUE INDEX uq_bilty_book_primary ON bilty_book(company_id, branch_id, bilty_type)
    WHERE is_primary = TRUE;

CREATE TRIGGER trg_bilty_book_updated_at
    BEFORE UPDATE ON bilty_book
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- fn_next_gr_no(p_book_id)
-- Atomically claims the next GR number from a bilty_book row.
-- Uses UPDATE ... RETURNING under a row-level lock so two
-- concurrent sessions can never receive the same number —
-- no separate reservation table is needed.
--
-- Returns: (gr_no TEXT, gr_number INTEGER)
--   gr_no     → fully formatted string  e.g. "MUM/0042/25"
--   gr_number → raw integer claimed     e.g. 42
--
-- Raises an exception if the book is inactive, completed, or
-- already exhausted — the caller must handle this in app code.
-- ============================================================
CREATE OR REPLACE FUNCTION fn_next_gr_no(p_book_id UUID)
RETURNS TABLE (gr_no TEXT, gr_number INTEGER)
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
    -- Lock the book row for this transaction — prevents any other
    -- concurrent call from reading the same current_number.
    SELECT current_number, to_number, prefix, postfix, digits, is_fixed
    INTO   v_current, v_to, v_prefix, v_postfix, v_digits, v_is_fixed
    FROM   bilty_book
    WHERE  book_id    = p_book_id
      AND  is_active  = TRUE
      AND  is_completed = FALSE
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'bilty_book % is not available (does not exist, inactive, or already completed)',
            p_book_id;
    END IF;

    IF v_current > v_to THEN
        UPDATE bilty_book SET is_completed = TRUE WHERE book_id = p_book_id;
        RAISE EXCEPTION
            'bilty_book % is exhausted — all numbers in the range have been used',
            p_book_id;
    END IF;

    -- Advance the counter (skip in fixed mode — number is reused intentionally)
    IF NOT v_is_fixed THEN
        UPDATE bilty_book
           SET current_number = current_number + 1,
               is_completed   = (current_number + 1 > v_to)
         WHERE book_id = p_book_id;
    END IF;

    -- Return formatted GR string + raw number
    RETURN QUERY SELECT
        COALESCE(v_prefix, '') || LPAD(v_current::TEXT, v_digits, '0') || COALESCE(v_postfix, ''),
        v_current;
END;
$$;


-- ============================================================
-- bilty_rate
-- Rate card that can be owned by EITHER a consignor OR a
-- consignee — exactly one of consignor_id / consignee_id must
-- be set (enforced by chk_bilty_rate_party below).
--
-- party_type  : CONSIGNOR | CONSIGNEE  (denorm for fast filtering)
-- rate_unit   : PER_KG | PER_NAG (package/piece)
-- labour_unit : PER_KG | PER_NAG | PER_BILTY
--
-- Active rate lookup (consignor side):
--   WHERE consignor_id = ? AND is_active = TRUE
--     AND effective_from <= CURRENT_DATE
--     AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
--
-- Active rate lookup (consignee side):
--   WHERE consignee_id = ? AND is_active = TRUE
--     AND effective_from <= CURRENT_DATE
--     AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
-- ============================================================
CREATE TABLE bilty_rate (
    rate_id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id              UUID        NOT NULL REFERENCES tenant_companies(company_id)  ON DELETE CASCADE,
    branch_id               UUID        NOT NULL REFERENCES tenant_branches(branch_id)    ON DELETE CASCADE,

    -- Exactly one of these two must be non-NULL (see constraint below)
    consignor_id            UUID        REFERENCES bilty_consignor(consignor_id)          ON DELETE CASCADE,
    consignee_id            UUID        REFERENCES bilty_consignee(consignee_id)          ON DELETE CASCADE,

    -- Denormalised party type — kept in sync with the FK set above
    -- Makes filtering by side trivial without a CASE expression
    party_type              VARCHAR(10) NOT NULL
                                CHECK (party_type IN ('CONSIGNOR', 'CONSIGNEE')),

    destination_city_id     UUID        NOT NULL REFERENCES master_city(city_id)          ON DELETE CASCADE,
    transport_id            UUID        REFERENCES master_transport(transport_id)          ON DELETE SET NULL,

    -- Freight
    rate                    NUMERIC     NOT NULL DEFAULT 0 CHECK (rate >= 0),
    rate_unit               VARCHAR(10) NOT NULL DEFAULT 'PER_KG'
                                CHECK (rate_unit IN ('PER_KG', 'PER_NAG')),
    minimum_weight_kg       NUMERIC     DEFAULT 0,
    freight_minimum_amount  NUMERIC     DEFAULT 0,

    -- Labour
    labour_rate             NUMERIC     NOT NULL DEFAULT 0 CHECK (labour_rate >= 0),
    labour_unit             VARCHAR(10) CHECK (labour_unit IN ('PER_KG', 'PER_NAG', 'PER_BILTY')),

    -- Surcharges
    dd_charge_per_kg        NUMERIC     DEFAULT 0,
    dd_charge_per_nag       NUMERIC     DEFAULT 0,
    bilty_charge            NUMERIC     DEFAULT 0,
    receiving_slip_charge   NUMERIC     DEFAULT 0,
    is_toll_tax_applicable  BOOLEAN     NOT NULL DEFAULT FALSE,
    toll_tax_amount         NUMERIC     DEFAULT 0,

    -- Flags
    is_no_charge            BOOLEAN     NOT NULL DEFAULT FALSE,

    -- Validity window
    effective_from          DATE        NOT NULL DEFAULT CURRENT_DATE,
    effective_to            DATE,

    is_active               BOOLEAN     NOT NULL DEFAULT TRUE,
    metadata                JSONB       NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by              UUID        REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by              UUID        REFERENCES iam_users(id) ON DELETE SET NULL,

    -- Exactly one party FK must be set; both NULL or both set are invalid
    CONSTRAINT chk_bilty_rate_party
        CHECK (
            (consignor_id IS NOT NULL AND consignee_id IS NULL AND party_type = 'CONSIGNOR')
            OR
            (consignee_id IS NOT NULL AND consignor_id IS NULL AND party_type = 'CONSIGNEE')
        ),

    -- One rate per party + destination city per start date
    -- Partial unique indexes below cover each side efficiently
    CONSTRAINT uq_bilty_rate_consignor
        UNIQUE NULLS NOT DISTINCT (company_id, branch_id, consignor_id, destination_city_id, effective_from),
    CONSTRAINT uq_bilty_rate_consignee
        UNIQUE NULLS NOT DISTINCT (company_id, branch_id, consignee_id, destination_city_id, effective_from)
);

CREATE INDEX idx_bilty_rate_company         ON bilty_rate(company_id);
CREATE INDEX idx_bilty_rate_branch          ON bilty_rate(company_id, branch_id);
CREATE INDEX idx_bilty_rate_consignor       ON bilty_rate(consignor_id) WHERE consignor_id IS NOT NULL;
CREATE INDEX idx_bilty_rate_consignee       ON bilty_rate(consignee_id) WHERE consignee_id IS NOT NULL;
CREATE INDEX idx_bilty_rate_city            ON bilty_rate(destination_city_id);
CREATE INDEX idx_bilty_rate_party_type      ON bilty_rate(company_id, branch_id, party_type);
CREATE INDEX idx_bilty_rate_active_cnr      ON bilty_rate(consignor_id, is_active)
    WHERE is_active = TRUE AND consignor_id IS NOT NULL;
CREATE INDEX idx_bilty_rate_active_cne      ON bilty_rate(consignee_id, is_active)
    WHERE is_active = TRUE AND consignee_id IS NOT NULL;

CREATE TRIGGER trg_bilty_rate_updated_at
    BEFORE UPDATE ON bilty_rate
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- bilty
-- Unified bilty table — handles both REGULAR (from bill-book)
-- and MANUAL (station bilty / hand-written) types.
--
-- bilty_type:
--   REGULAR  → GR via fn_next_gr_no(); book_id is set
--   MANUAL   → manually typed GR (book_id is NULL)
--
-- payment_mode:
--   PAID | TO-PAY | FOC (Free of Charge)
--
-- delivery_type:
--   DOOR | GODOWN
--
-- e_way_bill JSONB example:
--   { "ewb_no": "1234567890123", "valid_upto": "2026-05-10",
--     "is_valid": true, "vehicle_no": "MH12AB1234" }
--
-- Party columns (consignor_name, consignee_name, etc.) are
-- intentionally denormalised — they capture the value at
-- creation time so history stays accurate after master edits.
--
-- Soft-delete: set is_active=FALSE + deleted_at + deleted_by +
-- deletion_reason. Replaces old station_bilty_deleted table.
--
-- tracking_meta JSONB: free-form tracking data (GPS, scans…).
-- ============================================================
CREATE TABLE bilty (
    bilty_id                UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id              UUID            NOT NULL REFERENCES tenant_companies(company_id) ON DELETE RESTRICT,
    branch_id               UUID            NOT NULL REFERENCES tenant_branches(branch_id)   ON DELETE RESTRICT,

    -- ── GR / LR Number ─────────────────────────────────────
    gr_no                   VARCHAR(50)     NOT NULL,
    book_id                 UUID            REFERENCES bilty_book(book_id) ON DELETE SET NULL,
    bilty_type              VARCHAR(10)     NOT NULL DEFAULT 'REGULAR'
                                CHECK (bilty_type IN ('REGULAR', 'MANUAL')),
    bilty_date              DATE            NOT NULL DEFAULT CURRENT_DATE,

    -- ── Consignor (snapshot) ────────────────────────────────
    consignor_id            UUID            REFERENCES bilty_consignor(consignor_id) ON DELETE SET NULL,
    consignor_name          VARCHAR(255)    NOT NULL,
    consignor_gstin         VARCHAR(15),
    consignor_mobile        VARCHAR(15),

    -- ── Consignee (snapshot) ────────────────────────────────
    consignee_id            UUID            REFERENCES bilty_consignee(consignee_id) ON DELETE SET NULL,
    consignee_name          VARCHAR(255),
    consignee_gstin         VARCHAR(15),
    consignee_mobile        VARCHAR(15),

    -- ── Transport (snapshot) ────────────────────────────────
    transport_id            UUID            REFERENCES master_transport(transport_id) ON DELETE SET NULL,
    transport_name          VARCHAR(255),
    transport_gstin         VARCHAR(15),
    transport_mobile        VARCHAR(15),

    -- ── Route ───────────────────────────────────────────────
    from_city_id            UUID            REFERENCES master_city(city_id) ON DELETE SET NULL,
    to_city_id              UUID            REFERENCES master_city(city_id) ON DELETE SET NULL,

    -- ── Shipment details ────────────────────────────────────
    delivery_type           VARCHAR(10)     CHECK (delivery_type IN ('DOOR', 'GODOWN')),
    payment_mode            VARCHAR(10)     CHECK (payment_mode IN ('PAID', 'TO-PAY', 'FOC')),
    contain                 TEXT,
    invoice_no              VARCHAR(100),
    invoice_value           NUMERIC         DEFAULT 0,
    invoice_date            DATE,
    -- e_way_bills stores array of EWB detail objects, e.g.
    -- [{ "ewb_no": "1234567890123", "valid_upto": "2026-05-10", "vehicle_no": "MH12AB1234" }, ...]
    e_way_bills             JSONB           NOT NULL DEFAULT '[]',
    document_number         VARCHAR(100),
    no_of_pkg               INTEGER         NOT NULL DEFAULT 0,
    weight                  NUMERIC,                        -- billed weight
    actual_weight           NUMERIC,                        -- physical/actual weight
    rate                    NUMERIC,
    pvt_marks               TEXT,

    -- ── Charges ─────────────────────────────────────────────
    freight_amount          NUMERIC         DEFAULT 0,
    labour_rate             NUMERIC,
    labour_charge           NUMERIC         DEFAULT 0,
    bill_charge             NUMERIC         DEFAULT 0,
    toll_charge             NUMERIC         DEFAULT 0,
    dd_charge               NUMERIC         DEFAULT 0,
    pf_charge               NUMERIC         DEFAULT 0,
    other_charge            NUMERIC         DEFAULT 0,
    local_charge            NUMERIC         DEFAULT 0,      -- local delivery/handling charge
    discount_id             UUID            REFERENCES bilty_discount(discount_id) ON DELETE SET NULL,
    discount_percentage     NUMERIC         DEFAULT 0 CHECK (discount_percentage >= 0 AND discount_percentage <= 100),
    discount_amount         NUMERIC         DEFAULT 0 CHECK (discount_amount >= 0),
    total_amount            NUMERIC         DEFAULT 0,

    -- ── Template override ───────────────────────────────────
    -- If set, overrides the book-level template for this specific bilty
    template_id             UUID            REFERENCES bilty_template(template_id) ON DELETE SET NULL,

    -- ── Files ───────────────────────────────────────────────
    pdf_url                 TEXT,

    -- ── Save state ──────────────────────────────────────────
    saving_option           VARCHAR(10)     NOT NULL DEFAULT 'SAVE'
                                CHECK (saving_option IN ('SAVE', 'DRAFT', 'PRINT')),

    -- ── Overall status ──────────────────────────────────────
    -- Single source of truth for lifecycle position.
    status                  VARCHAR(20)     NOT NULL DEFAULT 'SAVED'
                                CHECK (status IN (
                                    'DRAFT',
                                    'SAVED',
                                    'DISPATCHED',
                                    'REACHED_HUB',
                                    'AT_GODOWN',
                                    'OUT_FOR_DELIVERY',
                                    'DELIVERED',
                                    'UNDELIVERED',
                                    'CANCELLED',
                                    'LOST'
                                )),

    -- ── Dispatch ────────────────────────────────────────────
    is_dispatched           BOOLEAN         NOT NULL DEFAULT FALSE,
    dispatched_at           TIMESTAMPTZ,
    dispatched_challan_no   VARCHAR(50),    -- denorm for quick challan look-ups
    dispatched_by           UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    -- ── Challan assignment ──────────────────────────────────
    -- challan_id and trip_sheet_id are plain UUID columns here.
    -- FK constraints to challan/challan_trip_sheet are added
    -- at the end of challan.sql (forward-reference workaround).
    challan_id              UUID,
    challan_branch_id       UUID            REFERENCES tenant_branches(branch_id) ON DELETE SET NULL,
    trip_sheet_id           UUID,
    challan_assigned_at     TIMESTAMPTZ,
    challan_assigned_by     UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    -- ── Kaat (onward transport charges) ─────────────────────
    -- kaat_amount = base + RS + bilty_chg + labour + other
    -- transit_profit = total_amount - kaat_amount - real_dd_charge
    kaat_rate               NUMERIC         DEFAULT 0,
    kaat_rate_type          VARCHAR(10)     DEFAULT NULL
                                CHECK (kaat_rate_type IS NULL OR kaat_rate_type IN ('PER_KG', 'PER_PKG')),
    kaat_weight_charged     NUMERIC         DEFAULT 0,
    kaat_base_amount        NUMERIC         DEFAULT 0,
    kaat_receiving_slip_charge NUMERIC      DEFAULT 0,
    kaat_bilty_charge       NUMERIC         DEFAULT 0,
    kaat_labour_rate        NUMERIC         DEFAULT 0,
    kaat_labour_rate_type   VARCHAR(10)     DEFAULT NULL
                                CHECK (kaat_labour_rate_type IS NULL OR kaat_labour_rate_type IN ('PER_KG', 'PER_PKG', 'PER_BILTY')),
    kaat_labour_charge      NUMERIC         DEFAULT 0,
    kaat_other_charges      JSONB           NOT NULL DEFAULT '[]',
    kaat_other_charges_total NUMERIC        DEFAULT 0,
    kaat_amount             NUMERIC         DEFAULT 0,
    real_dd_charge          NUMERIC         DEFAULT 0,
    transit_profit          NUMERIC         DEFAULT 0,

    -- ── Crossing proof ──────────────────────────────────────
    -- POHONCH = pohonch slip; CROSSING_BILTY = crossing bilty number
    crossing_proof_type     VARCHAR(16)     DEFAULT NULL
                                CHECK (crossing_proof_type IS NULL OR crossing_proof_type IN ('POHONCH', 'CROSSING_BILTY')),
    crossing_proof_ref      VARCHAR(100)    DEFAULT NULL,

    -- ── Hub arrival ─────────────────────────────────────────
    is_reached_hub          BOOLEAN         NOT NULL DEFAULT FALSE,
    reached_hub_at          TIMESTAMPTZ,
    reached_hub_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    -- ── Godown / destination branch ─────────────────────────
    is_at_godown            BOOLEAN         NOT NULL DEFAULT FALSE,
    at_godown_at            TIMESTAMPTZ,
    at_godown_by            UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    -- ── Out for delivery ────────────────────────────────────
    is_out_for_delivery     BOOLEAN         NOT NULL DEFAULT FALSE,
    out_for_delivery_at     TIMESTAMPTZ,
    out_for_delivery_by     UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    -- ── Final delivery ──────────────────────────────────────
    is_delivered            BOOLEAN         NOT NULL DEFAULT FALSE,
    delivered_at            TIMESTAMPTZ,
    delivered_by            UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    delivery_remark         TEXT,
    pod_image_url           TEXT,           -- proof-of-delivery photo

    -- ── Soft delete (replaces old station_bilty_deleted) ────
    is_active               BOOLEAN         NOT NULL DEFAULT TRUE,
    deleted_at              TIMESTAMPTZ,
    deleted_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    deletion_reason         TEXT,

    -- ── Free-form metadata + tracking extras ────────────────
    -- tracking_meta example:
    --   { "ewb_validated": true, "gps": {"lat": 28.6, "lng": 77.2} }
    tracking_meta           JSONB           NOT NULL DEFAULT '{}',
    remark                  TEXT,
    metadata                JSONB           NOT NULL DEFAULT '{}',

    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    -- GR number unique per company + branch
    UNIQUE (company_id, branch_id, gr_no),

    CONSTRAINT chk_bilty_crossing_proof CHECK (
        (crossing_proof_type IS NULL AND crossing_proof_ref IS NULL)
        OR
        (crossing_proof_type IS NOT NULL AND crossing_proof_ref IS NOT NULL)
    ),

    -- book_id required for REGULAR bilties
    CONSTRAINT chk_bilty_book_required
        CHECK (bilty_type = 'MANUAL' OR book_id IS NOT NULL)
);

-- Core lookups
CREATE INDEX idx_bilty_company          ON bilty(company_id);
CREATE INDEX idx_bilty_branch           ON bilty(company_id, branch_id);
CREATE INDEX idx_bilty_gr_no            ON bilty(gr_no);
CREATE INDEX idx_bilty_type             ON bilty(company_id, branch_id, bilty_type);
CREATE INDEX idx_bilty_status           ON bilty(company_id, branch_id, status);
CREATE INDEX idx_bilty_date             ON bilty(bilty_date DESC);
CREATE INDEX idx_bilty_book             ON bilty(book_id);

-- Party lookups
CREATE INDEX idx_bilty_consignor        ON bilty(consignor_id);
CREATE INDEX idx_bilty_consignee        ON bilty(consignee_id);

-- Route lookups
CREATE INDEX idx_bilty_from_city        ON bilty(from_city_id);
CREATE INDEX idx_bilty_to_city          ON bilty(to_city_id);

-- Lifecycle / tracking filter queries (partial indexes — small, fast)
CREATE INDEX idx_bilty_dispatched       ON bilty(company_id, branch_id, dispatched_at)
    WHERE is_dispatched = TRUE;
CREATE INDEX idx_bilty_reached_hub      ON bilty(company_id, branch_id, reached_hub_at)
    WHERE is_reached_hub = TRUE;
CREATE INDEX idx_bilty_at_godown        ON bilty(company_id, branch_id, at_godown_at)
    WHERE is_at_godown = TRUE;
CREATE INDEX idx_bilty_out_for_delivery ON bilty(company_id, branch_id, out_for_delivery_at)
    WHERE is_out_for_delivery = TRUE;
CREATE INDEX idx_bilty_delivered        ON bilty(company_id, branch_id, delivered_at)
    WHERE is_delivered = TRUE;

-- Soft-delete filter
CREATE INDEX idx_bilty_active           ON bilty(company_id, branch_id, is_active)
    WHERE is_active = TRUE;

-- Challan cross-reference
CREATE INDEX idx_bilty_challan_no           ON bilty(dispatched_challan_no)        WHERE dispatched_challan_no IS NOT NULL;
CREATE INDEX idx_bilty_challan_branch       ON bilty(challan_branch_id)            WHERE challan_branch_id IS NOT NULL;
CREATE INDEX idx_bilty_crossing_proof_ref   ON bilty(crossing_proof_ref)           WHERE crossing_proof_ref IS NOT NULL;
CREATE INDEX idx_bilty_crossing_proof_type  ON bilty(company_id, branch_id, crossing_proof_type) WHERE crossing_proof_type IS NOT NULL;
CREATE INDEX idx_bilty_kaat_amount          ON bilty(company_id, branch_id, kaat_amount) WHERE kaat_amount > 0;
CREATE INDEX idx_bilty_transit_profit       ON bilty(company_id, branch_id, transit_profit);

-- tracking_meta GIN (for jsonb path queries like @> '{"ewb_validated":true}')
CREATE INDEX idx_bilty_tracking_meta    ON bilty USING GIN (tracking_meta);

CREATE INDEX idx_bilty_template ON bilty(template_id) WHERE template_id IS NOT NULL;
CREATE INDEX idx_bilty_discount ON bilty(discount_id) WHERE discount_id IS NOT NULL;

CREATE TRIGGER trg_bilty_updated_at
    BEFORE UPDATE ON bilty
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- bilty_template
-- Print template master record. company + branch scoped.
-- template_type defines which screen/document the template is
-- rendered for. book_id optionally pins it to one bilty book.
-- Bilty books (template_id on bilty_book) define the default
-- template for that book; individual bilties can override with
-- their own template_id.
-- ============================================================
CREATE TABLE bilty_template (
    template_id     UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID            NOT NULL REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id       UUID            NOT NULL REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,
    code            VARCHAR(50)     NOT NULL,
    name            VARCHAR(150)    NOT NULL,
    description     TEXT,
    slug            VARCHAR(100)    NOT NULL,
    -- template_type: what this template is used to print
    --   REGULAR_BILTY      → standard book-based bilty print
    --   MANUAL_BILTY       → manual / station bilty print
    --   MONTHLY_CONSIGNOR  → monthly consignment bill for consignor
    --   MONTHLY_CONSIGNEE  → monthly consignment bill for consignee
    template_type   VARCHAR(30)     NOT NULL DEFAULT 'REGULAR_BILTY'
                        CONSTRAINT chk_bilty_template_type CHECK (
                            template_type IN (
                                'REGULAR_BILTY',
                                'MANUAL_BILTY',
                                'MONTHLY_CONSIGNOR',
                                'MONTHLY_CONSIGNEE'
                            )
                        ),
    -- Optional: pin to a specific bilty book.
    -- NULL = available to the whole branch.
    book_id         UUID            REFERENCES bilty_book(book_id) ON DELETE SET NULL,
    metadata        JSONB           NOT NULL DEFAULT '{}',
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    is_primary      BOOLEAN         NOT NULL DEFAULT FALSE,  -- one primary per (company, branch)
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
CREATE INDEX idx_bilty_template_type    ON bilty_template(company_id, branch_id, template_type);
CREATE INDEX idx_bilty_template_book    ON bilty_template(book_id) WHERE book_id IS NOT NULL;
CREATE UNIQUE INDEX uq_bilty_template_primary ON bilty_template(company_id, branch_id)
    WHERE is_primary = TRUE;

CREATE TRIGGER trg_bilty_template_updated_at
    BEFORE UPDATE ON bilty_template
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- bilty_discount
-- Discount master. Can be scoped to a specific bilty book via
-- bill_book_id (NULL = applies to all books in the branch).
-- percentage is applied to total_amount; result is capped at
-- max_amount_discounted; only applied if total_amount >=
-- minimum_amount.
-- ============================================================
CREATE TABLE bilty_discount (
    discount_id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id            UUID        NOT NULL REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id             UUID        NOT NULL REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,
    discount_code         VARCHAR(50) NOT NULL,
    percentage            NUMERIC     NOT NULL DEFAULT 0 CHECK (percentage >= 0 AND percentage <= 100),
    bill_book_id          UUID        REFERENCES bilty_book(book_id) ON DELETE SET NULL,
    max_amount_discounted NUMERIC     DEFAULT NULL CHECK (max_amount_discounted IS NULL OR max_amount_discounted >= 0),
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


-- ============================================================
-- DESIGN NOTES
-- ============================================================
--
-- 1. REGULAR vs MANUAL bilty
--    REGULAR: book_id is set; GR issued by fn_next_gr_no().
--    MANUAL:  book_id is NULL; GR is manually typed.
--    Both live in the same bilty table — filter on bilty_type.
--
--    bilty_book.bilty_type controls which kind of bilty a book
--    can be used for (REGULAR or MANUAL).
--    bilty_book.party_scope controls who can use the book:
--      COMMON    → shared; any user / any consignor/consignee
--      CONSIGNOR → locked to a specific consignor_id
--      CONSIGNEE → locked to a specific consignee_id
--    chk_bilty_book_party_scope enforces these rules at the DB level.
--
-- 2. Atomic GR number generation (fn_next_gr_no)
--    Call SELECT * FROM fn_next_gr_no('<book_id>') inside the
--    same transaction that INSERTs the bilty row.  The function
--    uses UPDATE ... FOR UPDATE to lock the book row, advances
--    current_number, and auto-marks is_completed when the last
--    number is consumed.  No reservation table, no race condition.
--
-- 3. Soft delete (replaces station_bilty_deleted)
--    Never hard-delete a bilty row.  Set:
--      is_active = FALSE, deleted_at = NOW(),
--      deleted_by = <user_id>, deletion_reason = '...'
--    All list queries MUST filter WHERE is_active = TRUE.
--
-- 4. Tracking lifecycle (status is the single source of truth)
--    DRAFT → SAVED → DISPATCHED → REACHED_HUB → AT_GODOWN
--    → OUT_FOR_DELIVERY → DELIVERED
--    Branch-offs: UNDELIVERED, LOST, CANCELLED
--    When updating status always update the matching boolean +
--    timestamp + _by columns (is_dispatched / dispatched_at …).
--
-- 5. Party snapshot vs. FK
--    consignor_id → bilty_consignor, consignee_id → bilty_consignee.
--    The _name / _gstin / _mobile columns snapshot the value at
--    creation time so history is never broken by master edits.
--
-- 6. bilty_rate — consignor OR consignee side
--    party_type = 'CONSIGNOR': consignor_id is set, consignee_id is NULL.
--    party_type = 'CONSIGNEE': consignee_id is set, consignor_id is NULL.
--    chk_bilty_rate_party enforces this at the DB level.
--    Active rate:
--      WHERE consignor_id = ? AND is_active = TRUE   -- consignor side
--        AND effective_from <= CURRENT_DATE
--        AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
--      WHERE consignee_id = ? AND is_active = TRUE   -- consignee side
--        AND effective_from <= CURRENT_DATE
--        AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
--
-- 7. e_way_bill shape (JSONB)
--    Minimum: { "ewb_no": "<13-digit>", "valid_upto": "YYYY-MM-DD" }
--    Extended: add "is_valid", "vehicle_no", "extended_at" as needed.
--
-- ============================================================
