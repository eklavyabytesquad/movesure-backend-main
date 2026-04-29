-- ============================================================
-- APP TABLES
-- app_module, app_tnt_module
-- Depends on: tenant.sql, iam.sql
-- ============================================================


-- ============================================================
-- app_module
-- ============================================================
CREATE TABLE app_module (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255)    NOT NULL,
    slug            VARCHAR(100)    NOT NULL UNIQUE,
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    meta            JSONB           NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL
);

CREATE INDEX idx_app_module_slug   ON app_module(slug);
CREATE INDEX idx_app_module_active ON app_module(is_active) WHERE is_active = TRUE;

CREATE TRIGGER trg_app_module_updated_at
    BEFORE UPDATE ON app_module
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- app_tnt_module
-- ============================================================
CREATE TABLE app_tnt_module (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID            NOT NULL REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    module_id       UUID            NOT NULL REFERENCES app_module(id)               ON DELETE CASCADE,
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    UNIQUE (company_id, module_id)
);

CREATE INDEX idx_app_tnt_module_company ON app_tnt_module(company_id);
CREATE INDEX idx_app_tnt_module_module  ON app_tnt_module(module_id);
CREATE INDEX idx_app_tnt_module_active  ON app_tnt_module(company_id, is_active)
    WHERE is_active = TRUE;

CREATE TRIGGER trg_app_tnt_module_updated_at
    BEFORE UPDATE ON app_tnt_module
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
