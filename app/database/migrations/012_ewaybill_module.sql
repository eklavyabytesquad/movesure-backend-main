-- ============================================================
-- Migration 012: E-Way Bill Module (v2 schema)
--
-- Safe to re-run: all statements use IF NOT EXISTS / DO blocks.
-- Run order: after tenant.sql, iam.sql (bilty/challan FKs optional)
--
-- Tables created:
--   ewb_token            → Masters India JWT persistence
--   ewb_settings         → Per-company GST/EWB config
--   ewb_records          → One row per EWB; bilty-linked; items as JSONB
--   ewb_validation_log   → Versioned NIC validation snapshots per EWB
--   ewb_events           → Append-only journey/action log
--   ewb_consolidated     → CEWBs; member numbers as JSONB (no junction table)
--
-- Views created:
--   v_ewb_expiring_soon, v_ewb_validation_history, v_ewb_journey,
--   v_bilty_ewb_summary, v_ewb_company_summary
--
-- Removed vs v1: ewb_items, ewb_extensions, ewb_transporter_updates,
--                ewb_consolidated_members (absorbed into JSONB / events)
-- ============================================================


-- ============================================================
-- ewb_token
-- ============================================================
CREATE TABLE IF NOT EXISTS ewb_token (
    token_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    username        VARCHAR(255)    NOT NULL UNIQUE,
    token           TEXT            NOT NULL,
    expires_at      TIMESTAMPTZ     NOT NULL,
    obtained_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_ewb_token_username ON ewb_token(username);
CREATE INDEX IF NOT EXISTS idx_ewb_token_expires  ON ewb_token(expires_at);
CREATE INDEX IF NOT EXISTS idx_ewb_token_active   ON ewb_token(is_active) WHERE is_active = TRUE;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_ewb_token_updated_at'
          AND tgrelid = 'ewb_token'::regclass
    ) THEN
        CREATE TRIGGER trg_ewb_token_updated_at
            BEFORE UPDATE ON ewb_token
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END $$;


-- ============================================================
-- ewb_settings
-- ============================================================
CREATE TABLE IF NOT EXISTS ewb_settings (
    settings_id             UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id              UUID            NOT NULL UNIQUE
                                REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    company_gstin           VARCHAR(15)     NOT NULL,
    auto_generate_ewb       BOOLEAN         NOT NULL DEFAULT FALSE,
    auto_validate_on_save   BOOLEAN         NOT NULL DEFAULT TRUE,
    alert_before_expiry_hrs INTEGER         NOT NULL DEFAULT 8,
    metadata                JSONB           NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_ewb_settings_company ON ewb_settings(company_id);
CREATE INDEX IF NOT EXISTS idx_ewb_settings_gstin   ON ewb_settings(company_gstin);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_ewb_settings_updated_at'
          AND tgrelid = 'ewb_settings'::regclass
    ) THEN
        CREATE TRIGGER trg_ewb_settings_updated_at
            BEFORE UPDATE ON ewb_settings
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END $$;


-- ============================================================
-- ewb_records
-- ============================================================
CREATE TABLE IF NOT EXISTS ewb_records (
    ewb_id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Scope
    company_id              UUID            NOT NULL
                                REFERENCES tenant_companies(company_id) ON DELETE RESTRICT,
    branch_id               UUID            NOT NULL
                                REFERENCES tenant_branches(branch_id)   ON DELETE RESTRICT,

    -- Bilty / challan links (forward-ref FKs added at bottom)
    bilty_id                UUID,
    challan_id              UUID,

    -- EWB identity
    eway_bill_number        VARCHAR(20)     NOT NULL,
    eway_bill_date          TIMESTAMPTZ,
    valid_upto              TIMESTAMPTZ,
    generated_by_gstin      VARCHAR(15),
    is_self_transfer        BOOLEAN         NOT NULL DEFAULT FALSE,

    -- Current NIC status
    ewb_status              VARCHAR(25)     NOT NULL DEFAULT 'FETCHED'
                                CHECK (ewb_status IN (
                                    'GENERATED','ACTIVE','EXTENDED','CONSOLIDATED',
                                    'TRANSPORTER_UPDATED','SELF_TRANSFERRED',
                                    'CANCELLED','EXPIRED','FETCHED','ERROR'
                                )),

    -- Last NIC error (populated when ewb_status = ERROR)
    last_error_code         VARCHAR(10),
    last_error_description  TEXT,

    -- Document details
    supply_type             VARCHAR(20),
    sub_supply_type         VARCHAR(50),
    document_type           VARCHAR(30),
    document_number         VARCHAR(20),
    document_date           DATE,

    -- Consignor snapshot
    gstin_of_consignor      VARCHAR(15),
    consignor_name          VARCHAR(255),
    pincode_of_consignor    VARCHAR(10),
    state_of_consignor      VARCHAR(100),

    -- Consignee snapshot
    gstin_of_consignee      VARCHAR(15),
    consignee_name          VARCHAR(255),
    pincode_of_consignee    VARCHAR(10),
    state_of_supply         VARCHAR(100),

    -- Amounts
    taxable_amount          NUMERIC         NOT NULL DEFAULT 0,
    total_invoice_value     NUMERIC         NOT NULL DEFAULT 0,
    cgst_amount             NUMERIC         NOT NULL DEFAULT 0,
    sgst_amount             NUMERIC         NOT NULL DEFAULT 0,
    igst_amount             NUMERIC         NOT NULL DEFAULT 0,
    cess_amount             NUMERIC         NOT NULL DEFAULT 0,
    cess_non_advol_amount   NUMERIC         NOT NULL DEFAULT 0,
    other_amount            NUMERIC         NOT NULL DEFAULT 0,

    -- Transport
    transportation_mode     VARCHAR(20),
    transportation_distance INTEGER,
    vehicle_number          VARCHAR(20),
    vehicle_type            VARCHAR(10)     DEFAULT 'Regular'
                                CHECK (vehicle_type IS NULL OR vehicle_type IN ('Regular','ODC')),

    -- Current transporter (updated on reassignment)
    transporter_id          VARCHAR(15),
    transporter_name        VARCHAR(255),
    transporter_doc_number  VARCHAR(30),
    transporter_doc_date    DATE,

    -- Items as JSONB (no separate ewb_items table)
    -- Shape: [{"product_name":...,"hsn_code":...,"quantity":...,...}]
    items_json              JSONB           NOT NULL DEFAULT '[]',

    -- Consolidated EWB reference (FK added below after ewb_consolidated)
    cewb_id                 UUID,

    -- PDF
    pdf_url                 TEXT,

    -- Raw NIC response (reflects latest call)
    raw_response            JSONB           NOT NULL DEFAULT '{}',

    -- Flexible extra
    metadata                JSONB           NOT NULL DEFAULT '{}',

    -- Audit
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE indexname = 'uq_ewb_records_number_company'
    ) THEN
        CREATE UNIQUE INDEX uq_ewb_records_number_company
            ON ewb_records(company_id, eway_bill_number);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_ewb_records_company         ON ewb_records(company_id);
CREATE INDEX IF NOT EXISTS idx_ewb_records_branch          ON ewb_records(company_id, branch_id);
CREATE INDEX IF NOT EXISTS idx_ewb_records_bilty           ON ewb_records(bilty_id) WHERE bilty_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ewb_records_challan         ON ewb_records(challan_id) WHERE challan_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ewb_records_ewb_number      ON ewb_records(eway_bill_number);
CREATE INDEX IF NOT EXISTS idx_ewb_records_status          ON ewb_records(company_id, ewb_status);
CREATE INDEX IF NOT EXISTS idx_ewb_records_valid_upto      ON ewb_records(valid_upto);
CREATE INDEX IF NOT EXISTS idx_ewb_records_document_number ON ewb_records(company_id, document_number);
CREATE INDEX IF NOT EXISTS idx_ewb_records_consignor_gstin ON ewb_records(gstin_of_consignor);
CREATE INDEX IF NOT EXISTS idx_ewb_records_consignee_gstin ON ewb_records(gstin_of_consignee);
CREATE INDEX IF NOT EXISTS idx_ewb_records_transporter     ON ewb_records(transporter_id)
    WHERE transporter_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ewb_records_vehicle         ON ewb_records(vehicle_number)
    WHERE vehicle_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ewb_records_self_transfer   ON ewb_records(company_id, is_self_transfer)
    WHERE is_self_transfer = TRUE;
CREATE INDEX IF NOT EXISTS idx_ewb_records_expiring
    ON ewb_records(valid_upto)
    WHERE ewb_status IN ('ACTIVE', 'EXTENDED');

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_ewb_records_updated_at'
          AND tgrelid = 'ewb_records'::regclass
    ) THEN
        CREATE TRIGGER trg_ewb_records_updated_at
            BEFORE UPDATE ON ewb_records
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END $$;


-- ============================================================
-- ewb_validation_log
-- ============================================================
CREATE TABLE IF NOT EXISTS ewb_validation_log (
    log_id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    ewb_id              UUID            NOT NULL
                            REFERENCES ewb_records(ewb_id) ON DELETE CASCADE,
    eway_bill_number    VARCHAR(20)     NOT NULL,
    company_id          UUID            NOT NULL
                            REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id           UUID            NOT NULL
                            REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,
    version_no          INTEGER         NOT NULL DEFAULT 1,
    nic_status          VARCHAR(25),
    valid_upto          TIMESTAMPTZ,
    generated_by_gstin  VARCHAR(15),
    vehicle_number      VARCHAR(20),
    transporter_id      VARCHAR(15),
    error_code          VARCHAR(10),
    error_description   TEXT,
    triggered_by        VARCHAR(30)     DEFAULT 'manual'
                            CHECK (triggered_by IN (
                                'manual','auto','on_generate','on_bilty_save'
                            )),
    raw_response        JSONB           NOT NULL DEFAULT '{}',
    validated_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE indexname = 'uq_ewb_validation_log_version'
    ) THEN
        CREATE UNIQUE INDEX uq_ewb_validation_log_version
            ON ewb_validation_log(ewb_id, version_no);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_ewb_val_log_ewb          ON ewb_validation_log(ewb_id);
CREATE INDEX IF NOT EXISTS idx_ewb_val_log_number       ON ewb_validation_log(eway_bill_number);
CREATE INDEX IF NOT EXISTS idx_ewb_val_log_company      ON ewb_validation_log(company_id);
CREATE INDEX IF NOT EXISTS idx_ewb_val_log_branch       ON ewb_validation_log(company_id, branch_id);
CREATE INDEX IF NOT EXISTS idx_ewb_val_log_status       ON ewb_validation_log(eway_bill_number, nic_status);
CREATE INDEX IF NOT EXISTS idx_ewb_val_log_validated_at ON ewb_validation_log(validated_at);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_ewb_validation_log_updated_at'
          AND tgrelid = 'ewb_validation_log'::regclass
    ) THEN
        CREATE TRIGGER trg_ewb_validation_log_updated_at
            BEFORE UPDATE ON ewb_validation_log
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END $$;


-- ============================================================
-- ewb_events
-- ============================================================
CREATE TABLE IF NOT EXISTS ewb_events (
    event_id            UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    ewb_id              UUID            NOT NULL
                            REFERENCES ewb_records(ewb_id) ON DELETE CASCADE,
    eway_bill_number    VARCHAR(20)     NOT NULL,
    company_id          UUID            NOT NULL
                            REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id           UUID            NOT NULL
                            REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,
    event_type          VARCHAR(25)     NOT NULL
                            CHECK (event_type IN (
                                'GENERATED','FETCHED','VALIDATED',
                                'CONSOLIDATED','TRANSPORTER_UPDATED','TRANSPORTER_PDF',
                                'EXTENDED','SELF_TRANSFERRED','CANCELLED','ERROR'
                            )),
    event_data          JSONB           NOT NULL DEFAULT '{}',
    reference_id        UUID,
    reference_type      VARCHAR(30),
    notes               TEXT,
    raw_response        JSONB           NOT NULL DEFAULT '{}',
    occurred_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_ewb_events_ewb         ON ewb_events(ewb_id);
CREATE INDEX IF NOT EXISTS idx_ewb_events_number      ON ewb_events(eway_bill_number);
CREATE INDEX IF NOT EXISTS idx_ewb_events_company     ON ewb_events(company_id);
CREATE INDEX IF NOT EXISTS idx_ewb_events_branch      ON ewb_events(company_id, branch_id);
CREATE INDEX IF NOT EXISTS idx_ewb_events_type        ON ewb_events(ewb_id, event_type);
CREATE INDEX IF NOT EXISTS idx_ewb_events_occurred_at ON ewb_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_ewb_events_reference   ON ewb_events(reference_id)
    WHERE reference_id IS NOT NULL;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_ewb_events_updated_at'
          AND tgrelid = 'ewb_events'::regclass
    ) THEN
        CREATE TRIGGER trg_ewb_events_updated_at
            BEFORE UPDATE ON ewb_events
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END $$;


-- ============================================================
-- ewb_consolidated
-- ============================================================
CREATE TABLE IF NOT EXISTS ewb_consolidated (
    cewb_id                 UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id              UUID            NOT NULL
                                REFERENCES tenant_companies(company_id) ON DELETE RESTRICT,
    branch_id               UUID            NOT NULL
                                REFERENCES tenant_branches(branch_id)   ON DELETE RESTRICT,
    cewb_number             VARCHAR(20)     NOT NULL,
    cewb_date               TIMESTAMPTZ,
    vehicle_number          VARCHAR(20)     NOT NULL,
    mode_of_transport       VARCHAR(20)     NOT NULL,
    transporter_doc_number  VARCHAR(30)     NOT NULL,
    transporter_doc_date    DATE            NOT NULL,
    place_of_consignor      VARCHAR(255)    NOT NULL,
    state_of_consignor      VARCHAR(100)    NOT NULL,
    data_source             VARCHAR(5)      NOT NULL DEFAULT 'E',
    -- Member EWBs as JSONB: [{"eway_bill_number":"...","ewb_id":"uuid-or-null"},...]
    ewb_numbers             JSONB           NOT NULL DEFAULT '[]',
    pdf_url                 TEXT,
    cewb_status             VARCHAR(15)     NOT NULL DEFAULT 'ACTIVE'
                                CHECK (cewb_status IN ('ACTIVE','CANCELLED','EXPIRED')),
    raw_response            JSONB           NOT NULL DEFAULT '{}',
    metadata                JSONB           NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE indexname = 'uq_ewb_consolidated_number_company'
    ) THEN
        CREATE UNIQUE INDEX uq_ewb_consolidated_number_company
            ON ewb_consolidated(company_id, cewb_number);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_ewb_consolidated_company ON ewb_consolidated(company_id);
CREATE INDEX IF NOT EXISTS idx_ewb_consolidated_branch  ON ewb_consolidated(company_id, branch_id);
CREATE INDEX IF NOT EXISTS idx_ewb_consolidated_number  ON ewb_consolidated(cewb_number);
CREATE INDEX IF NOT EXISTS idx_ewb_consolidated_vehicle ON ewb_consolidated(vehicle_number);
CREATE INDEX IF NOT EXISTS idx_ewb_consolidated_status  ON ewb_consolidated(company_id, cewb_status);
CREATE INDEX IF NOT EXISTS idx_ewb_consolidated_members_gin
    ON ewb_consolidated USING GIN (ewb_numbers);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_ewb_consolidated_updated_at'
          AND tgrelid = 'ewb_consolidated'::regclass
    ) THEN
        CREATE TRIGGER trg_ewb_consolidated_updated_at
            BEFORE UPDATE ON ewb_consolidated
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END $$;


-- ============================================================
-- Forward-reference FKs (bilty / challan / cewb)
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_ewb_records_bilty'
    ) THEN
        BEGIN
            ALTER TABLE ewb_records
                ADD CONSTRAINT fk_ewb_records_bilty
                FOREIGN KEY (bilty_id) REFERENCES bilty(bilty_id) ON DELETE SET NULL;
        EXCEPTION WHEN undefined_table THEN
            RAISE NOTICE 'bilty table not found — skipping fk_ewb_records_bilty';
        END;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_ewb_records_challan'
    ) THEN
        BEGIN
            ALTER TABLE ewb_records
                ADD CONSTRAINT fk_ewb_records_challan
                FOREIGN KEY (challan_id) REFERENCES challan(challan_id) ON DELETE SET NULL;
        EXCEPTION WHEN undefined_table THEN
            RAISE NOTICE 'challan table not found — skipping fk_ewb_records_challan';
        END;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_ewb_records_cewb'
    ) THEN
        ALTER TABLE ewb_records
            ADD CONSTRAINT fk_ewb_records_cewb
            FOREIGN KEY (cewb_id) REFERENCES ewb_consolidated(cewb_id) ON DELETE SET NULL;
    END IF;
END $$;


-- ============================================================
-- Views
-- ============================================================

-- EWBs in NIC extension window (±8 h around expiry)
CREATE OR REPLACE VIEW v_ewb_expiring_soon AS
SELECT
    r.ewb_id,
    r.company_id,
    r.branch_id,
    r.eway_bill_number,
    r.bilty_id,
    r.valid_upto,
    r.vehicle_number,
    r.transporter_id,
    r.transporter_name,
    r.ewb_status,
    ROUND(EXTRACT(EPOCH FROM (r.valid_upto - NOW())) / 3600, 2) AS hours_remaining
FROM ewb_records r
WHERE r.ewb_status IN ('ACTIVE', 'EXTENDED')
  AND r.valid_upto BETWEEN NOW() - INTERVAL '8 hours'
                       AND NOW() + INTERVAL '8 hours';

-- Versioned validation history (newest first)
CREATE OR REPLACE VIEW v_ewb_validation_history AS
SELECT
    vl.log_id,
    vl.ewb_id,
    vl.eway_bill_number,
    vl.company_id,
    vl.branch_id,
    vl.version_no,
    vl.nic_status,
    vl.valid_upto,
    vl.error_code,
    vl.error_description,
    vl.triggered_by,
    vl.validated_at,
    vl.created_by
FROM ewb_validation_log vl
ORDER BY vl.ewb_id, vl.version_no DESC;

-- Journey timeline (oldest first)
CREATE OR REPLACE VIEW v_ewb_journey AS
SELECT
    e.event_id,
    e.ewb_id,
    e.eway_bill_number,
    e.company_id,
    e.branch_id,
    e.event_type,
    e.event_data,
    e.notes,
    e.occurred_at,
    e.created_by
FROM ewb_events e
ORDER BY e.ewb_id, e.occurred_at ASC;

-- EWB count / status breakdown per bilty
CREATE OR REPLACE VIEW v_bilty_ewb_summary AS
SELECT
    r.bilty_id,
    r.company_id,
    r.branch_id,
    COUNT(*)                                                    AS total_ewbs,
    COUNT(*) FILTER (WHERE r.ewb_status = 'ACTIVE')            AS active,
    COUNT(*) FILTER (WHERE r.ewb_status = 'EXTENDED')          AS extended,
    COUNT(*) FILTER (WHERE r.ewb_status = 'CANCELLED')         AS cancelled,
    COUNT(*) FILTER (WHERE r.ewb_status = 'EXPIRED')           AS expired,
    COUNT(*) FILTER (WHERE r.ewb_status = 'ERROR')             AS error,
    MIN(r.valid_upto)                                           AS earliest_expiry,
    MAX(r.valid_upto)                                           AS latest_expiry
FROM ewb_records r
WHERE r.bilty_id IS NOT NULL
GROUP BY r.bilty_id, r.company_id, r.branch_id;

-- Per-company status breakdown (dashboard)
CREATE OR REPLACE VIEW v_ewb_company_summary AS
SELECT
    company_id,
    ewb_status,
    COUNT(*)                 AS ewb_count,
    SUM(total_invoice_value) AS total_invoice_value,
    MIN(valid_upto)          AS earliest_expiry,
    MAX(created_at)          AS last_activity_at
FROM ewb_records
GROUP BY company_id, ewb_status;
