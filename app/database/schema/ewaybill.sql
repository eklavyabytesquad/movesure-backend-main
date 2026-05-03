-- ============================================================
-- E-WAY BILL MODULE — Full Schema (v2)
-- ============================================================
--
-- DESIGN PHILOSOPHY
-- -----------------
-- Primary use-case is EWB *validation* attached to bilties.
-- Each bilty can carry multiple EWB numbers.
-- Validation of the same EWB is versioned over time (NIC status
-- can change: ACTIVE → CANCELLED → error "not your EWB").
-- Every action and every NIC response is logged in full.
-- Items are embedded as JSONB inside ewb_records — no child table.
-- Consolidated member EWB numbers are stored as JSONB inside
-- ewb_consolidated — no junction table.
--
-- TABLES
-- ------
--   ewb_token            → Masters India JWT (one row per MI username)
--   ewb_settings         → Per-company config (GSTIN, flags)
--   ewb_records          → One row per EWB number, bilty-linked,
--                          items_json JSONB, current NIC state
--   ewb_validation_log   → Versioned NIC validation snapshots per EWB
--                          (every fetch = new row, status may change each time)
--   ewb_events           → Full journey log per EWB
--                          (GENERATED, VALIDATED, CONSOLIDATED,
--                           TRANSPORTER_UPDATED, EXTENDED,
--                           SELF_TRANSFERRED, FETCHED, CANCELLED, ERROR)
--   ewb_consolidated     → Consolidated EWBs; member numbers in JSONB
--
-- All tables carry: company_id, branch_id, created_at, updated_at,
--                   created_by, updated_by, raw_response JSONB.
--
-- Depends on: tenant.sql, iam.sql
-- set_updated_at() trigger function defined in tenant.sql.
-- ============================================================


-- ============================================================
-- ewb_token
-- ============================================================
-- Persists the Masters India JWT token to the database so that
-- all worker processes / pods share the same valid token.
-- One row per Masters India username (typically one row total).
-- The application layers memory-cache and disk-file on top of this.
-- ============================================================
CREATE TABLE ewb_token (
    token_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Masters India account that owns this token
    username        VARCHAR(255)    NOT NULL UNIQUE,

    -- The raw JWT string sent in the Authorization: JWT … header
    token           TEXT            NOT NULL,

    -- Decoded from the JWT `exp` claim — UTC
    expires_at      TIMESTAMPTZ     NOT NULL,

    -- When this row was last successfully refreshed
    obtained_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- Quick flag — set FALSE if refresh fails so the app knows
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,

    -- Audit
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL
);

CREATE INDEX idx_ewb_token_username   ON ewb_token(username);
CREATE INDEX idx_ewb_token_expires    ON ewb_token(expires_at);
CREATE INDEX idx_ewb_token_active     ON ewb_token(is_active) WHERE is_active = TRUE;

CREATE TRIGGER trg_ewb_token_updated_at
    BEFORE UPDATE ON ewb_token
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- ewb_settings
-- ============================================================
-- Per-company EWB configuration.
-- Stores the GSTIN used when calling Masters India, the MI account
-- details, and feature toggles for the company / branch.
--
-- company_gstin   : sourced from tenant_companies.gstin at setup time;
--                   duplicated here so EWB calls never need a JOIN.
-- mi_username     : Masters India account (defaults to the global one);
--                   kept for future multi-account support.
-- auto_attach_bilty: if TRUE, auto-generate EWB when a bilty is created.
-- ============================================================
CREATE TABLE ewb_settings (
    settings_id         UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    company_id          UUID            NOT NULL UNIQUE
                            REFERENCES tenant_companies(company_id) ON DELETE CASCADE,

    -- GSTIN used as the `userGstin` / `gstin` parameter in all API calls
    company_gstin       VARCHAR(15)     NOT NULL,

    -- Masters India account
    mi_username         VARCHAR(255)    NOT NULL DEFAULT 'eklavyasingh9870@gmail.com',

    -- Feature flags
    auto_attach_bilty   BOOLEAN         NOT NULL DEFAULT FALSE,
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,

    -- Flexible extra config (API timeout overrides, default doc types, etc.)
    metadata            JSONB           NOT NULL DEFAULT '{}',

    -- Audit
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL
);

CREATE INDEX idx_ewb_settings_company ON ewb_settings(company_id);
CREATE INDEX idx_ewb_settings_gstin   ON ewb_settings(company_gstin);

CREATE TRIGGER trg_ewb_settings_updated_at
    BEFORE UPDATE ON ewb_settings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- ewb_records
-- ============================================================
-- One row per unique EWB number per company.
--
-- This is the *current state* of an EWB — always reflects the
-- latest known NIC data.  The full change history lives in
-- ewb_validation_log (versioned snapshots) and ewb_events (journey).
--
-- bilty_id: the bilty this EWB is attached to.
--           One bilty → many ewb_records (each row = one EWB number).
--           NULL for EWBs created standalone (not linked to a bilty).
--
-- items_json: NIC itemList embedded as JSONB.  No separate items table.
--   Example:
--   [
--     {"product_name":"Cotton Bales","hsn_code":"5201","quantity":10,
--      "unit_of_product":"BLS","taxable_amount":50000,
--      "cgst_rate":0,"sgst_rate":0,"igst_rate":5}
--   ]
--
-- ewb_status values (mirrors NIC):
--   GENERATED    → freshly created on NIC by us
--   ACTIVE       → currently valid (confirmed by last NIC fetch)
--   EXTENDED     → validity extended at least once
--   CONSOLIDATED → included in a CEWB
--   TRANSPORTER_UPDATED → transporter reassigned
--   SELF_TRANSFERRED    → same-GSTIN self-transfer EWB
--   CANCELLED    → cancelled on NIC
--   EXPIRED      → past validUpto
--   FETCHED      → pulled from NIC (not generated by us; just linked)
--   ERROR        → last NIC call returned an error (e.g. "not your EWB")
-- ============================================================
CREATE TABLE ewb_records (
    ewb_id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- ── Scope ────────────────────────────────────────────────
    company_id              UUID            NOT NULL
                                REFERENCES tenant_companies(company_id) ON DELETE RESTRICT,
    branch_id               UUID            NOT NULL
                                REFERENCES tenant_branches(branch_id)   ON DELETE RESTRICT,

    -- ── Bilty link ───────────────────────────────────────────
    -- FK to bilty added at end of file (forward-reference workaround)
    bilty_id                UUID,           -- NULL = standalone EWB
    challan_id              UUID,           -- set when dispatched on a challan

    -- ── EWB identity ─────────────────────────────────────────
    eway_bill_number        VARCHAR(20)     NOT NULL,   -- 12-digit NIC EWB number
    eway_bill_date          TIMESTAMPTZ,                -- as returned by NIC
    valid_upto              TIMESTAMPTZ,                -- current validity (updated on extension)
    generated_by_gstin      VARCHAR(15),                -- NIC `generatedBy` field
    is_self_transfer        BOOLEAN         NOT NULL DEFAULT FALSE,
    -- TRUE when gstin_of_consignor = gstin_of_consignee

    -- ── Current NIC status ───────────────────────────────────
    ewb_status              VARCHAR(25)     NOT NULL DEFAULT 'FETCHED'
                                CHECK (ewb_status IN (
                                    'GENERATED',
                                    'ACTIVE',
                                    'EXTENDED',
                                    'CONSOLIDATED',
                                    'TRANSPORTER_UPDATED',
                                    'SELF_TRANSFERRED',
                                    'CANCELLED',
                                    'EXPIRED',
                                    'FETCHED',
                                    'ERROR'
                                )),

    -- ── Last NIC error (populated when ewb_status = ERROR) ───
    last_error_code         VARCHAR(10),
    last_error_description  TEXT,

    -- ── Document details ─────────────────────────────────────
    supply_type             VARCHAR(20),
    sub_supply_type         VARCHAR(50),
    document_type           VARCHAR(30),
    document_number         VARCHAR(20),
    document_date           DATE,

    -- ── Consignor snapshot ───────────────────────────────────
    gstin_of_consignor      VARCHAR(15),
    consignor_name          VARCHAR(255),
    pincode_of_consignor    VARCHAR(10),
    state_of_consignor      VARCHAR(100),

    -- ── Consignee snapshot ───────────────────────────────────
    gstin_of_consignee      VARCHAR(15),
    consignee_name          VARCHAR(255),
    pincode_of_consignee    VARCHAR(10),
    state_of_supply         VARCHAR(100),

    -- ── Amounts ──────────────────────────────────────────────
    taxable_amount          NUMERIC         NOT NULL DEFAULT 0,
    total_invoice_value     NUMERIC         NOT NULL DEFAULT 0,
    cgst_amount             NUMERIC         NOT NULL DEFAULT 0,
    sgst_amount             NUMERIC         NOT NULL DEFAULT 0,
    igst_amount             NUMERIC         NOT NULL DEFAULT 0,
    cess_amount             NUMERIC         NOT NULL DEFAULT 0,
    cess_non_advol_amount   NUMERIC         NOT NULL DEFAULT 0,
    other_amount            NUMERIC         NOT NULL DEFAULT 0,

    -- ── Transport ────────────────────────────────────────────
    transportation_mode     VARCHAR(20),
    transportation_distance INTEGER,
    vehicle_number          VARCHAR(20),
    vehicle_type            VARCHAR(10)     DEFAULT 'Regular'
                                CHECK (vehicle_type IS NULL OR vehicle_type IN ('Regular','ODC')),

    -- ── Current transporter (updated on reassignment) ────────
    transporter_id          VARCHAR(15),
    transporter_name        VARCHAR(255),
    transporter_doc_number  VARCHAR(30),
    transporter_doc_date    DATE,

    -- ── Items (NIC itemList — no separate table) ─────────────
    -- Array of item objects; see comment above for shape.
    items_json              JSONB           NOT NULL DEFAULT '[]',

    -- ── Consolidated EWB reference ───────────────────────────
    -- Set when this EWB is included in a CEWB.
    cewb_id                 UUID,           -- FK to ewb_consolidated added below

    -- ── PDF ──────────────────────────────────────────────────
    pdf_url                 TEXT,

    -- ── Last raw NIC response (always kept up to date) ───────
    raw_response            JSONB           NOT NULL DEFAULT '{}',

    -- ── Flexible extra ───────────────────────────────────────
    metadata                JSONB           NOT NULL DEFAULT '{}',

    -- ── Audit ────────────────────────────────────────────────
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL
);

-- One EWB number is unique per company
CREATE UNIQUE INDEX uq_ewb_records_number_company
    ON ewb_records(company_id, eway_bill_number);

CREATE INDEX idx_ewb_records_company         ON ewb_records(company_id);
CREATE INDEX idx_ewb_records_branch          ON ewb_records(company_id, branch_id);
CREATE INDEX idx_ewb_records_bilty           ON ewb_records(bilty_id) WHERE bilty_id IS NOT NULL;
CREATE INDEX idx_ewb_records_challan         ON ewb_records(challan_id) WHERE challan_id IS NOT NULL;
CREATE INDEX idx_ewb_records_ewb_number      ON ewb_records(eway_bill_number);
CREATE INDEX idx_ewb_records_status          ON ewb_records(company_id, ewb_status);
CREATE INDEX idx_ewb_records_valid_upto      ON ewb_records(valid_upto);
CREATE INDEX idx_ewb_records_document_number ON ewb_records(company_id, document_number);
CREATE INDEX idx_ewb_records_consignor_gstin ON ewb_records(gstin_of_consignor);
CREATE INDEX idx_ewb_records_consignee_gstin ON ewb_records(gstin_of_consignee);
CREATE INDEX idx_ewb_records_transporter     ON ewb_records(transporter_id)
    WHERE transporter_id IS NOT NULL;
CREATE INDEX idx_ewb_records_vehicle         ON ewb_records(vehicle_number)
    WHERE vehicle_number IS NOT NULL;
CREATE INDEX idx_ewb_records_self_transfer   ON ewb_records(company_id, is_self_transfer)
    WHERE is_self_transfer = TRUE;

-- Partial index: fast expiry-alert queries
CREATE INDEX idx_ewb_records_expiring
    ON ewb_records(valid_upto)
    WHERE ewb_status IN ('ACTIVE', 'EXTENDED');

CREATE TRIGGER trg_ewb_records_updated_at
    BEFORE UPDATE ON ewb_records
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- ewb_validation_log
-- ============================================================
-- Versioned snapshot of every NIC validation/fetch call for an EWB.
--
-- Each time we call Masters India to fetch or validate an EWB a new
-- row is inserted here with a sequential version_no.  This preserves
-- the full time-based history of NIC responses:
--
--   v1  ACTIVE    valid_upto = 2026-05-03
--   v2  ACTIVE    valid_upto = 2026-05-05  (after extension)
--   v3  CANCELLED error = "312: EWB already cancelled"
--   v4  ERROR     error = "338: Not authorised to view this EWB"
--
-- The app always upserts ewb_records to the latest state AND inserts
-- a new row here — never updates old rows in this table.
-- ============================================================
CREATE TABLE ewb_validation_log (
    log_id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Parent EWB record
    ewb_id              UUID            NOT NULL
                            REFERENCES ewb_records(ewb_id) ON DELETE CASCADE,

    -- Denormalised for direct queries without joining ewb_records
    eway_bill_number    VARCHAR(20)     NOT NULL,
    company_id          UUID            NOT NULL
                            REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id           UUID            NOT NULL
                            REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,

    -- ── Version (auto-incremented per EWB in application layer) ─
    version_no          INTEGER         NOT NULL DEFAULT 1,
    -- version_no = 1 is the first validation, 2 is the next, etc.

    -- ── NIC status at this point in time ─────────────────────
    nic_status          VARCHAR(25),    -- ACTIVE / CANCELLED / EXPIRED / ERROR / etc.
    valid_upto          TIMESTAMPTZ,    -- validity returned in this call
    generated_by_gstin  VARCHAR(15),
    vehicle_number      VARCHAR(20),
    transporter_id      VARCHAR(15),

    -- ── Error (when NIC returned an error response) ───────────
    error_code          VARCHAR(10),        -- NIC error code e.g. "338"
    error_description   TEXT,               -- NIC error message

    -- ── Who triggered this check ─────────────────────────────
    triggered_by        VARCHAR(30)     DEFAULT 'manual'
                            CHECK (triggered_by IN (
                                'manual',       -- user clicked "validate" on the UI
                                'auto',         -- background cron / scheduled check
                                'on_generate',  -- auto-check after EWB generation
                                'on_bilty_save' -- auto-check when bilty is saved
                            )),

    -- ── Full raw NIC response ─────────────────────────────────
    raw_response        JSONB           NOT NULL DEFAULT '{}',

    -- ── Audit ────────────────────────────────────────────────
    validated_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL
);

-- Uniqueness: one version per EWB per check (version_no incremented by app)
CREATE UNIQUE INDEX uq_ewb_validation_log_version
    ON ewb_validation_log(ewb_id, version_no);

CREATE INDEX idx_ewb_val_log_ewb          ON ewb_validation_log(ewb_id);
CREATE INDEX idx_ewb_val_log_number       ON ewb_validation_log(eway_bill_number);
CREATE INDEX idx_ewb_val_log_company      ON ewb_validation_log(company_id);
CREATE INDEX idx_ewb_val_log_branch       ON ewb_validation_log(company_id, branch_id);
CREATE INDEX idx_ewb_val_log_status       ON ewb_validation_log(eway_bill_number, nic_status);
CREATE INDEX idx_ewb_val_log_validated_at ON ewb_validation_log(validated_at);

CREATE TRIGGER trg_ewb_validation_log_updated_at
    BEFORE UPDATE ON ewb_validation_log
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- ewb_events
-- ============================================================
-- Full journey / action log for every EWB.
-- Every operation (generate, validate, consolidate, transporter
-- update, extend, self-transfer, cancel, error) inserts a new row.
-- Rows are never updated — this is an append-only audit trail.
--
-- event_type values:
--   GENERATED           → EWB created via our generate endpoint
--   FETCHED             → EWB pulled from NIC for the first time
--   VALIDATED           → NIC fetch/validate call (check status)
--   CONSOLIDATED        → EWB included in a Consolidated EWB
--   TRANSPORTER_UPDATED → Transporter assigned / reassigned
--   TRANSPORTER_PDF     → Same as above but with PDF 2-call flow
--   EXTENDED            → Validity extended
--   SELF_TRANSFERRED    → Self-transfer (same GSTIN consignor + consignee)
--   CANCELLED           → EWB cancelled on NIC
--   ERROR               → Any NIC error response
--
-- event_data JSONB holds the action-specific payload:
--   VALIDATED         → { "nic_status": "ACTIVE", "valid_upto": "…", "version_no": 3 }
--   TRANSPORTER_UPDATED → { "transporter_id": "…", "transporter_name": "…", "pdf_found": true }
--   EXTENDED          → { "new_valid_upto": "…", "remaining_distance": 250, "reason": "…" }
--   CONSOLIDATED      → { "cewb_number": "…", "cewb_id": "…" }
--   ERROR             → { "error_code": "338", "error_description": "…" }
-- ============================================================
CREATE TABLE ewb_events (
    event_id            UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Parent EWB
    ewb_id              UUID            NOT NULL
                            REFERENCES ewb_records(ewb_id) ON DELETE CASCADE,

    -- Denormalised for fast filtering
    eway_bill_number    VARCHAR(20)     NOT NULL,
    company_id          UUID            NOT NULL
                            REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id           UUID            NOT NULL
                            REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,

    -- ── Event type ───────────────────────────────────────────
    event_type          VARCHAR(25)     NOT NULL
                            CHECK (event_type IN (
                                'GENERATED',
                                'FETCHED',
                                'VALIDATED',
                                'CONSOLIDATED',
                                'TRANSPORTER_UPDATED',
                                'TRANSPORTER_PDF',
                                'EXTENDED',
                                'SELF_TRANSFERRED',
                                'CANCELLED',
                                'ERROR'
                            )),

    -- ── Event-specific data (see comment above for shape) ────
    event_data          JSONB           NOT NULL DEFAULT '{}',

    -- ── Cross-reference (set when event links to another table) ─
    -- e.g. cewb_id for CONSOLIDATED, ewb_validation_log.log_id for VALIDATED
    reference_id        UUID,
    reference_type      VARCHAR(30),    -- 'ewb_consolidated' / 'ewb_validation_log' / etc.

    -- ── Notes (optional human-readable note) ─────────────────
    notes               TEXT,

    -- ── Full raw NIC response ─────────────────────────────────
    raw_response        JSONB           NOT NULL DEFAULT '{}',

    -- ── When this event occurred ─────────────────────────────
    occurred_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- ── Audit ────────────────────────────────────────────────
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL
);

CREATE INDEX idx_ewb_events_ewb         ON ewb_events(ewb_id);
CREATE INDEX idx_ewb_events_number      ON ewb_events(eway_bill_number);
CREATE INDEX idx_ewb_events_company     ON ewb_events(company_id);
CREATE INDEX idx_ewb_events_branch      ON ewb_events(company_id, branch_id);
CREATE INDEX idx_ewb_events_type        ON ewb_events(ewb_id, event_type);
CREATE INDEX idx_ewb_events_occurred_at ON ewb_events(occurred_at);
CREATE INDEX idx_ewb_events_reference   ON ewb_events(reference_id) WHERE reference_id IS NOT NULL;

CREATE TRIGGER trg_ewb_events_updated_at
    BEFORE UPDATE ON ewb_events
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- ewb_consolidated
-- ============================================================
-- One row per Consolidated E-Way Bill (CEWB).
-- Member EWB numbers are stored as a JSONB array — no junction table.
--
-- ewb_numbers JSONB shape:
--   [
--     { "eway_bill_number": "321012345678", "ewb_id": "<uuid-or-null>" },
--     { "eway_bill_number": "321012345679", "ewb_id": null }
--   ]
--   ewb_id is NULL when the member EWB was generated externally.
-- ============================================================
CREATE TABLE ewb_consolidated (
    cewb_id                 UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- ── Scope ────────────────────────────────────────────────
    company_id              UUID            NOT NULL
                                REFERENCES tenant_companies(company_id) ON DELETE RESTRICT,
    branch_id               UUID            NOT NULL
                                REFERENCES tenant_branches(branch_id)   ON DELETE RESTRICT,

    -- ── NIC-assigned CEWB number ─────────────────────────────
    cewb_number             VARCHAR(20)     NOT NULL,
    cewb_date               TIMESTAMPTZ,

    -- ── Transport at consolidation time ──────────────────────
    vehicle_number          VARCHAR(20)     NOT NULL,
    mode_of_transport       VARCHAR(20)     NOT NULL,
    transporter_doc_number  VARCHAR(30)     NOT NULL,
    transporter_doc_date    DATE            NOT NULL,
    place_of_consignor      VARCHAR(255)    NOT NULL,
    state_of_consignor      VARCHAR(100)    NOT NULL,
    data_source             VARCHAR(5)      NOT NULL DEFAULT 'E',

    -- ── Member EWB numbers (see comment above for shape) ─────
    ewb_numbers             JSONB           NOT NULL DEFAULT '[]',

    -- ── PDF ──────────────────────────────────────────────────
    pdf_url                 TEXT,

    -- ── Status ───────────────────────────────────────────────
    cewb_status             VARCHAR(15)     NOT NULL DEFAULT 'ACTIVE'
                                CHECK (cewb_status IN ('ACTIVE','CANCELLED','EXPIRED')),

    -- ── Raw NIC response ─────────────────────────────────────
    raw_response            JSONB           NOT NULL DEFAULT '{}',

    -- ── Flexible extra ───────────────────────────────────────
    metadata                JSONB           NOT NULL DEFAULT '{}',

    -- ── Audit ────────────────────────────────────────────────
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX uq_ewb_consolidated_number_company
    ON ewb_consolidated(company_id, cewb_number);

CREATE INDEX idx_ewb_consolidated_company ON ewb_consolidated(company_id);
CREATE INDEX idx_ewb_consolidated_branch  ON ewb_consolidated(company_id, branch_id);
CREATE INDEX idx_ewb_consolidated_number  ON ewb_consolidated(cewb_number);
CREATE INDEX idx_ewb_consolidated_vehicle ON ewb_consolidated(vehicle_number);
CREATE INDEX idx_ewb_consolidated_status  ON ewb_consolidated(company_id, cewb_status);
-- GIN index to search inside ewb_numbers JSONB array
CREATE INDEX idx_ewb_consolidated_members_gin
    ON ewb_consolidated USING GIN (ewb_numbers);

CREATE TRIGGER trg_ewb_consolidated_updated_at
    BEFORE UPDATE ON ewb_consolidated
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- Forward-reference FK: ewb_records → bilty / challan / cewb
-- Run after bilty.sql and challan.sql have been loaded.
-- ============================================================
-- ALTER TABLE ewb_records
--     ADD CONSTRAINT fk_ewb_records_bilty
--     FOREIGN KEY (bilty_id) REFERENCES bilty(bilty_id) ON DELETE SET NULL;
--
-- ALTER TABLE ewb_records
--     ADD CONSTRAINT fk_ewb_records_challan
--     FOREIGN KEY (challan_id) REFERENCES challan(challan_id) ON DELETE SET NULL;
--
-- ALTER TABLE ewb_records
--     ADD CONSTRAINT fk_ewb_records_cewb
--     FOREIGN KEY (cewb_id) REFERENCES ewb_consolidated(cewb_id) ON DELETE SET NULL;


-- ============================================================
-- Views
-- ============================================================

-- EWBs entering NIC extension window (±8 h around expiry)
CREATE VIEW v_ewb_expiring_soon AS
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

-- Full validation version history for an EWB (ordered newest first)
CREATE VIEW v_ewb_validation_history AS
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

-- Journey timeline for an EWB (ordered oldest first)
CREATE VIEW v_ewb_journey AS
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

-- EWB summary per bilty (how many EWBs and their statuses)
CREATE VIEW v_bilty_ewb_summary AS
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

-- Per-company EWB count breakdown (dashboard)
CREATE VIEW v_ewb_company_summary AS
SELECT
    company_id,
    ewb_status,
    COUNT(*)                 AS ewb_count,
    SUM(total_invoice_value) AS total_invoice_value,
    MIN(valid_upto)          AS earliest_expiry,
    MAX(created_at)          AS last_activity_at
FROM ewb_records
GROUP BY company_id, ewb_status;
