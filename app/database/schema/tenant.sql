-- ============================================================
-- TENANT TABLES
-- tenant_companies, tenant_branches
-- Run this first — other tables depend on these.
-- ============================================================

-- ============================================================
-- SHARED: updated_at trigger function
-- Defined here (first file) — used by iam, app tables too.
-- ============================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


-- ============================================================
-- tenant_companies
-- ============================================================
CREATE TABLE tenant_companies (
    company_id      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255)    NOT NULL,
    address         TEXT,
    phone_number    VARCHAR(20),
    phone_verified  BOOLEAN         NOT NULL DEFAULT FALSE,
    email           VARCHAR(255)    UNIQUE,
    gstin           VARCHAR(15),
    metadata        JSONB           NOT NULL DEFAULT '{}',
    plan            VARCHAR(50),
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by      UUID,
    updated_by      UUID
);

CREATE UNIQUE INDEX uq_tenant_companies_email ON tenant_companies(email) WHERE email IS NOT NULL;
CREATE INDEX        idx_tenant_companies_gstin ON tenant_companies(gstin);

CREATE TRIGGER trg_tenant_companies_updated_at
    BEFORE UPDATE ON tenant_companies
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- tenant_branches
-- ============================================================
CREATE TABLE tenant_branches (
    branch_id       UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255)    NOT NULL,
    address         TEXT,
    branch_code     VARCHAR(50),
    company_id      UUID            NOT NULL REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_type     VARCHAR(20)     NOT NULL DEFAULT 'branch'
                        CHECK (branch_type IN ('primary', 'hub', 'branch')),
    metadata        JSONB           NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by      UUID,
    updated_by      UUID
);

CREATE INDEX idx_tenant_branches_company ON tenant_branches(company_id);
CREATE INDEX idx_tenant_branches_code    ON tenant_branches(branch_code);
CREATE UNIQUE INDEX uq_tenant_branches_code_company ON tenant_branches(company_id, branch_code);

CREATE TRIGGER trg_tenant_branches_updated_at
    BEFORE UPDATE ON tenant_branches
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
