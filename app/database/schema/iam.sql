-- ============================================================
-- IAM TABLES
-- iam_users, iam_permission, iam_user_permission
-- Depends on: tenant.sql
-- ============================================================


-- ============================================================
-- iam_users
-- ============================================================
CREATE TABLE iam_users (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255)    NOT NULL UNIQUE,
    password        TEXT            NOT NULL,
    full_name       VARCHAR(255),
    image_url       TEXT,
    post_in_office  VARCHAR(100),
    company_id      UUID            REFERENCES tenant_companies(company_id) ON DELETE SET NULL,
    branch_id       UUID            REFERENCES tenant_branches(branch_id)   ON DELETE SET NULL,
    metadata        JSONB           NOT NULL DEFAULT '{}',
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_iam_users_company ON iam_users(company_id);
CREATE INDEX idx_iam_users_branch  ON iam_users(branch_id);
CREATE INDEX idx_iam_users_email   ON iam_users(email);
CREATE INDEX idx_iam_users_active  ON iam_users(is_active) WHERE is_active = TRUE;

CREATE TRIGGER trg_iam_users_updated_at
    BEFORE UPDATE ON iam_users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- iam_permission
-- ============================================================
CREATE TABLE iam_permission (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID            REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id       UUID            REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,
    module          VARCHAR(100)    NOT NULL,
    action          VARCHAR(50)     NOT NULL,
    scope           VARCHAR(50),
    slug            VARCHAR(150),   -- optional shorthand, e.g. "master:city:create"
    meta            JSONB           NOT NULL DEFAULT '{}',
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    UNIQUE (module, action, scope)
);

CREATE UNIQUE INDEX uq_iam_permission_slug    ON iam_permission(slug) WHERE slug IS NOT NULL;
CREATE INDEX        idx_iam_permission_module  ON iam_permission(module);
CREATE INDEX        idx_iam_permission_company ON iam_permission(company_id);
CREATE INDEX        idx_iam_permission_branch  ON iam_permission(company_id, branch_id);
CREATE INDEX        idx_iam_permission_active  ON iam_permission(is_active) WHERE is_active = TRUE;

CREATE TRIGGER trg_iam_permission_updated_at
    BEFORE UPDATE ON iam_permission
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- iam_user_permission
-- ============================================================
CREATE TABLE iam_user_permission (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID            NOT NULL REFERENCES iam_users(id)       ON DELETE CASCADE,
    permission_id   UUID            NOT NULL REFERENCES iam_permission(id)  ON DELETE CASCADE,
    company_id      UUID            REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id       UUID            REFERENCES tenant_branches(branch_id)   ON DELETE CASCADE,
    reason          TEXT,
    granted_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by      UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    UNIQUE (user_id, permission_id)
);

CREATE INDEX idx_iam_user_perm_user       ON iam_user_permission(user_id);
CREATE INDEX idx_iam_user_perm_permission ON iam_user_permission(permission_id);
CREATE INDEX idx_iam_user_perm_company    ON iam_user_permission(company_id);
CREATE INDEX idx_iam_user_perm_branch     ON iam_user_permission(company_id, branch_id);
CREATE INDEX idx_iam_user_perm_expires    ON iam_user_permission(expires_at)
    WHERE expires_at IS NOT NULL;

CREATE TRIGGER trg_iam_user_permission_updated_at
    BEFORE UPDATE ON iam_user_permission
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
