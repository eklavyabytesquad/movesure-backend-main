-- ============================================================
-- MASTER DATA TABLES
-- master_state, master_city,
-- master_transport, master_city_wise_transport
--
-- Depends on: tenant.sql (tenant_companies, tenant_branches)
--             iam.sql    (iam_users — for created_by/updated_by)
-- ============================================================


-- ============================================================
-- master_state
-- One row = one state scoped to a company + branch.
-- total_city_count is kept in sync automatically by trigger.
-- ============================================================
CREATE TABLE master_state (
    state_id            UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID            NOT NULL REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id           UUID            NOT NULL REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,
    state_name          VARCHAR(100)    NOT NULL,
    state_code          VARCHAR(10)     NOT NULL,
    total_city_count    INTEGER         NOT NULL DEFAULT 0 CHECK (total_city_count >= 0),
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by          UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    -- state code must be unique within a company + branch scope
    UNIQUE (company_id, branch_id, state_code)
);

CREATE INDEX idx_master_state_company     ON master_state(company_id);
CREATE INDEX idx_master_state_branch      ON master_state(company_id, branch_id);
CREATE INDEX idx_master_state_code        ON master_state(state_code);
CREATE INDEX idx_master_state_active      ON master_state(is_active) WHERE is_active = TRUE;

CREATE TRIGGER trg_master_state_updated_at
    BEFORE UPDATE ON master_state
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- master_city
-- One row = one city scoped to a company + branch + state.
-- ============================================================
CREATE TABLE master_city (
    city_id         UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID            NOT NULL REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id       UUID            NOT NULL REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,
    state_id        UUID            NOT NULL REFERENCES master_state(state_id)       ON DELETE CASCADE,
    city_name       VARCHAR(150)    NOT NULL,
    city_code       VARCHAR(20)     NOT NULL,
    city_pin_code   VARCHAR(10),
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    -- city code must be unique within a company + branch scope
    UNIQUE (company_id, branch_id, city_code)
);

CREATE INDEX idx_master_city_company   ON master_city(company_id);
CREATE INDEX idx_master_city_branch    ON master_city(company_id, branch_id);
CREATE INDEX idx_master_city_state     ON master_city(state_id);
CREATE INDEX idx_master_city_pin       ON master_city(city_pin_code);
CREATE INDEX idx_master_city_active    ON master_city(is_active) WHERE is_active = TRUE;

CREATE TRIGGER trg_master_city_updated_at
    BEFORE UPDATE ON master_city
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- Trigger: keep master_state.total_city_count in sync
-- Fires after INSERT / DELETE / UPDATE (state_id change) on
-- master_city and recalculates the count for affected states.
-- ============================================================
CREATE OR REPLACE FUNCTION fn_sync_state_city_count()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    affected_state_id UUID;
BEGIN
    -- Determine which state_id to recount
    IF TG_OP = 'DELETE' THEN
        affected_state_id := OLD.state_id;
    ELSIF TG_OP = 'INSERT' THEN
        affected_state_id := NEW.state_id;
    ELSE
        -- UPDATE: if state_id changed recount old state too
        IF OLD.state_id IS DISTINCT FROM NEW.state_id THEN
            UPDATE master_state
               SET total_city_count = (
                   SELECT COUNT(*) FROM master_city
                    WHERE state_id = OLD.state_id
               )
             WHERE state_id = OLD.state_id;
        END IF;
        affected_state_id := NEW.state_id;
    END IF;

    UPDATE master_state
       SET total_city_count = (
           SELECT COUNT(*) FROM master_city
            WHERE state_id = affected_state_id
       )
     WHERE state_id = affected_state_id;

    RETURN NULL; -- AFTER trigger, return value ignored
END;
$$;

CREATE TRIGGER trg_master_city_sync_count
    AFTER INSERT OR UPDATE OF state_id OR DELETE ON master_city
    FOR EACH ROW EXECUTE FUNCTION fn_sync_state_city_count();


-- ============================================================
-- master_transport
-- Transport vendor/partner master, company + branch scoped.
-- mobile_number_owner JSONB: [{"name":"...", "mobile":"..."}]
-- ============================================================
CREATE TABLE master_transport (
    transport_id            UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    transport_code          VARCHAR(50)     NOT NULL,
    company_id              UUID            NOT NULL REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id               UUID            NOT NULL REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,
    transport_name          VARCHAR(255)    NOT NULL,
    gstin                   VARCHAR(15),
    mobile_number_owner     JSONB           NOT NULL DEFAULT '[]',
    website                 TEXT,
    address                 TEXT,
    metadata                JSONB           NOT NULL DEFAULT '{}',
    is_active               BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    -- transport code must be unique within a company + branch
    UNIQUE (company_id, branch_id, transport_code)
);

CREATE INDEX idx_master_transport_company   ON master_transport(company_id);
CREATE INDEX idx_master_transport_branch    ON master_transport(company_id, branch_id);
CREATE INDEX idx_master_transport_gstin     ON master_transport(gstin);
CREATE INDEX idx_master_transport_active    ON master_transport(is_active) WHERE is_active = TRUE;

CREATE TRIGGER trg_master_transport_updated_at
    BEFORE UPDATE ON master_transport
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- master_city_wise_transport
-- Links a transport vendor to a specific city for a branch.
-- branch_mobile JSONB: [{"label":"booking","mobile":"..."}]
-- ============================================================
CREATE TABLE master_city_wise_transport (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID            NOT NULL REFERENCES tenant_companies(company_id)  ON DELETE CASCADE,
    branch_id       UUID            NOT NULL REFERENCES tenant_branches(branch_id)    ON DELETE CASCADE,
    city_id         UUID            NOT NULL REFERENCES master_city(city_id)          ON DELETE CASCADE,
    transport_id    UUID            NOT NULL REFERENCES master_transport(transport_id) ON DELETE CASCADE,
    branch_mobile   JSONB           NOT NULL DEFAULT '[]',
    address         TEXT,
    manager_name    VARCHAR(255),

    -- ── Kaat rate card (auto-fills bilty kaat charges at dispatch) ──
    kaat_rate               NUMERIC         DEFAULT 0 CHECK (kaat_rate IS NULL OR kaat_rate >= 0),
    kaat_rate_type          VARCHAR(10)     NOT NULL DEFAULT 'PER_KG'
                                CHECK (kaat_rate_type IN ('PER_KG', 'PER_PKG')),
    minimum_weight_kg       NUMERIC         DEFAULT 0 CHECK (minimum_weight_kg IS NULL OR minimum_weight_kg >= 0),
    dd_charge_rate          NUMERIC         DEFAULT 0 CHECK (dd_charge_rate IS NULL OR dd_charge_rate >= 0),
    dd_charge_rate_type     VARCHAR(10)     NOT NULL DEFAULT 'FIXED'
                                CHECK (dd_charge_rate_type IN ('FIXED', 'PER_KG', 'PER_PKG')),
    dd_minimum_charge       NUMERIC         DEFAULT 0 CHECK (dd_minimum_charge IS NULL OR dd_minimum_charge >= 0),
    receiving_slip_charge   NUMERIC         DEFAULT 0 CHECK (receiving_slip_charge IS NULL OR receiving_slip_charge >= 0),
    kaat_bilty_charge       NUMERIC         DEFAULT 0 CHECK (kaat_bilty_charge IS NULL OR kaat_bilty_charge >= 0),
    kaat_labour_rate        NUMERIC         DEFAULT 0 CHECK (kaat_labour_rate IS NULL OR kaat_labour_rate >= 0),
    kaat_labour_rate_type   VARCHAR(10)     NOT NULL DEFAULT 'PER_KG'
                                CHECK (kaat_labour_rate_type IN ('PER_KG', 'PER_PKG', 'PER_BILTY')),
    other_standard_charges  JSONB           NOT NULL DEFAULT '[]',
    content_types           JSONB           NOT NULL DEFAULT '[]',
    kaat_effective_from     DATE            DEFAULT CURRENT_DATE,
    kaat_effective_to       DATE            DEFAULT NULL,

    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    -- one transport entry per city per branch (no duplicate city+transport combos)
    UNIQUE (company_id, branch_id, city_id, transport_id)
);

CREATE INDEX idx_master_cwt_company     ON master_city_wise_transport(company_id);
CREATE INDEX idx_master_cwt_branch      ON master_city_wise_transport(company_id, branch_id);
CREATE INDEX idx_master_cwt_city        ON master_city_wise_transport(city_id);
CREATE INDEX idx_master_cwt_transport   ON master_city_wise_transport(transport_id);
CREATE INDEX idx_master_cwt_active              ON master_city_wise_transport(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_master_cwt_kaat_city           ON master_city_wise_transport(company_id, branch_id, city_id, kaat_rate_type) WHERE kaat_rate > 0;
CREATE INDEX idx_master_cwt_content_types       ON master_city_wise_transport USING GIN (content_types);
CREATE INDEX idx_master_cwt_other_std_charges   ON master_city_wise_transport USING GIN (other_standard_charges);

CREATE TRIGGER trg_master_city_wise_transport_updated_at
    BEFORE UPDATE ON master_city_wise_transport
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
