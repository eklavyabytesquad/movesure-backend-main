# movesure-backend-main


my thinking for supabase table - 
tenant.companies - company_id, Name, Address, phone number , phone verified , email,  GSTIN, metadata, plan , created_at, updated_at, created_by, updated_by.
tenant.branches  - branch_id, name, address, branch_code , company_id , branch_type (primary,hub,branch),   metadata. , created_at, updated_at, created_by, updated_by.
iam.users - id, created_at , updated_at , image url , email , password, Full Name, Post in office , company_id , branch_id , metadata , is_active 
iam.permission - id , module , action , scope , meta , created_at , updated_at , is_active , created_by , updated_by
iam.user_permission - id , userid , permission_id , reason, granted_by , created_at , expires_at (optional) , updated_at , created by , updated_by.
app.module  - id , name , slug , is_active , meta , created_at , updated_at , created_by , updated_by.
app.tnt_module - id , company_id , module_id , is_active, created_at , updated_at , craeted_by , updated_by.
-- ============================================================
-- auth_sessions
-- One row = one logged-in device/browser
-- ============================================================
CREATE TABLE auth.sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES iam_users(id) ON DELETE CASCADE,
    company_id      UUID NOT NULL REFERENCES tnt_companies(id) ON DELETE CASCADE,

    ip_address      INET,
    user_agent      TEXT,
    device_name     VARCHAR(100),               -- "Chrome on Windows", "iPhone"
    device_type     VARCHAR(20) DEFAULT 'web'
                        CHECK (device_type IN ('web', 'mobile', 'api')),

    status          VARCHAR(20) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'expired', 'revoked')),
    expires_at      TIMESTAMPTZ NOT NULL,       -- e.g. NOW() + INTERVAL '30 days'
    revoked_at      TIMESTAMPTZ,

    last_active_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sessions_user    ON auth_sessions(user_id);
CREATE INDEX idx_sessions_active  ON auth_sessions(user_id, status)
    WHERE status = 'active';


-- ============================================================
-- auth_tokens
-- Access token (short-lived) + Refresh token (long-lived)
-- NEVER store the raw token — only its SHA-256 hash
-- ============================================================
CREATE TABLE auth.tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES auth_sessions(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES iam_users(id) ON DELETE CASCADE,

    type            VARCHAR(20) NOT NULL
                        CHECK (type IN (
                            'access',           -- 15 min JWT
                            'refresh',          -- 7–30 days, rotated on use
                            'password_reset',   -- one-time, 1 hour
                            'email_verify'      -- one-time, 24 hours
                        )),

    token_hash      VARCHAR(64) NOT NULL UNIQUE, -- SHA-256 of raw token
    expires_at      TIMESTAMPTZ NOT NULL,
    is_revoked      BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at      TIMESTAMPTZ,
    last_used_at    TIMESTAMPTZ,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tokens_hash      ON auth_tokens(token_hash);
CREATE INDEX idx_tokens_session   ON auth_tokens(session_id);
CREATE INDEX idx_tokens_user_type ON auth_tokens(user_id, type)
    WHERE is_revoked = FALSE;


-- ============================================================
-- auth_security_events
-- Simple append-only log — never update or delete rows
-- ============================================================
CREATE TABLE auth.security_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES iam_users(id) ON DELETE SET NULL,
    session_id      UUID REFERENCES auth_sessions(id) ON DELETE SET NULL,

    event_type      VARCHAR(50) NOT NULL
                        CHECK (event_type IN (
                            'login_success',
                            'login_failed',
                            'logout',
                            'token_refreshed',
                            'token_revoked',
                            'password_reset',
                            'password_changed',
                            'session_revoked',
                            'account_locked'
                        )),

    ip_address      INET,
    meta            JSONB NOT NULL DEFAULT '{}', -- any extra context

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sec_events_user ON auth_security_events(user_id, created_at DESC);
-- ============================================================
-- SCHEMA
-- ============================================================
CREATE SCHEMA IF NOT EXISTS logs;


-- ============================================================
-- logs.request_log
-- One row per API request. Links every audit entry to a
-- specific HTTP call, caller, device, and timestamp.
-- ============================================================
CREATE TABLE logs.request_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Who made the call
    user_id         UUID        REFERENCES iam.users(id) ON DELETE SET NULL,
    session_id      UUID        REFERENCES auth.sessions(id) ON DELETE SET NULL,
    company_id      UUID        REFERENCES tenant.companies(company_id) ON DELETE SET NULL,
    branch_id       UUID        REFERENCES tenant.branches(branch_id) ON DELETE SET NULL,

    -- What was called
    method          VARCHAR(10) NOT NULL,               -- GET, POST, PUT, PATCH, DELETE
    path            TEXT        NOT NULL,               -- /api/v1/users/123
    query_params    JSONB       NOT NULL DEFAULT '{}',  -- ?page=2&filter=active
    request_body    JSONB,                              -- sanitised payload (no passwords)

    -- Result
    status_code     SMALLINT    NOT NULL,               -- 200, 404, 422, 500 …
    error_message   TEXT,                               -- only populated on errors

    -- Context
    ip_address      INET,
    user_agent      TEXT,
    duration_ms     INTEGER,                            -- response time in ms
    correlation_id  UUID,                               -- pass-through from X-Request-ID header

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_reqlog_user        ON logs.request_log(user_id, created_at DESC);
CREATE INDEX idx_reqlog_path        ON logs.request_log(path, created_at DESC);
CREATE INDEX idx_reqlog_status      ON logs.request_log(status_code, created_at DESC);
CREATE INDEX idx_reqlog_company     ON logs.request_log(company_id, created_at DESC);
CREATE INDEX idx_reqlog_correlation ON logs.request_log(correlation_id);


-- ============================================================
-- logs.audit_log
-- One row per table-row that was created / updated / deleted.
-- A single API call can produce many audit_log rows if it
-- touches multiple records or multiple tables.
-- ============================================================
CREATE TABLE logs.audit_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Link back to the HTTP call that caused this change
    request_log_id  UUID        REFERENCES logs.request_log(id) ON DELETE SET NULL,

    -- Who, where, when
    user_id         UUID        REFERENCES iam.users(id) ON DELETE SET NULL,
    company_id      UUID        REFERENCES tenant.companies(company_id) ON DELETE SET NULL,
    acted_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- What table / row was affected
    table_schema    VARCHAR(63) NOT NULL,               -- e.g. 'iam', 'tenant'
    table_name      VARCHAR(63) NOT NULL,               -- e.g. 'users', 'branches'
    record_id       TEXT        NOT NULL,               -- PK value of the changed row

    -- What kind of change
    action          VARCHAR(10) NOT NULL
                        CHECK (action IN ('INSERT', 'UPDATE', 'DELETE', 'SELECT')),

    -- Full before/after snapshots (nullable for INSERT / DELETE respectively)
    old_data        JSONB,                              -- NULL on INSERT
    new_data        JSONB,                              -- NULL on DELETE

    -- Human-readable summary for quick scanning
    summary         TEXT,                               -- e.g. 'Updated user email'

    -- Any extra context your app wants to attach
    meta            JSONB       NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_audit_table     ON logs.audit_log(table_schema, table_name, record_id);
CREATE INDEX idx_audit_user      ON logs.audit_log(user_id, acted_at DESC);
CREATE INDEX idx_audit_company   ON logs.audit_log(company_id, acted_at DESC);
CREATE INDEX idx_audit_action    ON logs.audit_log(action, acted_at DESC);
CREATE INDEX idx_audit_request   ON logs.audit_log(request_log_id);
CREATE INDEX idx_audit_acted_at  ON logs.audit_log(acted_at DESC);


-- ============================================================
-- logs.audit_field_change
-- One row per column that actually changed within an UPDATE.
-- Makes it trivial to ask "who last changed this email?"
-- without diffing JSONB blobs.
-- ============================================================
CREATE TABLE logs.audit_field_change (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_log_id    UUID        NOT NULL
                        REFERENCES logs.audit_log(id) ON DELETE CASCADE,

    field_name      VARCHAR(63) NOT NULL,   -- column name, e.g. 'email'
    old_value       TEXT,                   -- cast to text for searchability
    new_value       TEXT,
    data_type       VARCHAR(63)             -- 'text', 'boolean', 'uuid', etc.
);

CREATE INDEX idx_fieldchg_audit      ON logs.audit_field_change(audit_log_id);
CREATE INDEX idx_fieldchg_field      ON logs.audit_field_change(field_name);
CREATE INDEX idx_fieldchg_field_val  ON logs.audit_field_change(field_name, new_value);


-- ============================================================
-- IMMUTABILITY — prevent anyone from editing or deleting logs
-- ============================================================
CREATE RULE no_update_request_log AS ON UPDATE TO logs.request_log DO INSTEAD NOTHING;
CREATE RULE no_delete_request_log AS ON DELETE TO logs.request_log DO INSTEAD NOTHING;

CREATE RULE no_update_audit_log   AS ON UPDATE TO logs.audit_log   DO INSTEAD NOTHING;
CREATE RULE no_delete_audit_log   AS ON DELETE TO logs.audit_log   DO INSTEAD NOTHING;

CREATE RULE no_update_field_chg   AS ON UPDATE TO logs.audit_field_change DO INSTEAD NOTHING;
CREATE RULE no_delete_field_chg   AS ON DELETE TO logs.audit_field_change DO INSTEAD NOTHING;


-- ============================================================
-- HELPER FUNCTION
-- Call this from your app/trigger after any DML operation.
-- Pass old_row / new_row as JSONB; it writes audit_log +
-- audit_field_change in one shot.
-- ============================================================
CREATE OR REPLACE FUNCTION logs.write_audit(
    p_request_log_id  UUID,
    p_user_id         UUID,
    p_company_id      UUID,
    p_table_schema    TEXT,
    p_table_name      TEXT,
    p_record_id       TEXT,
    p_action          TEXT,
    p_old_data        JSONB,
    p_new_data        JSONB,
    p_summary         TEXT   DEFAULT NULL,
    p_meta            JSONB  DEFAULT '{}'
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_audit_id  UUID;
    v_key       TEXT;
BEGIN
    -- 1. Insert the audit_log row
    INSERT INTO logs.audit_log (
        request_log_id, user_id, company_id,
        table_schema, table_name, record_id,
        action, old_data, new_data, summary, meta
    )
    VALUES (
        p_request_log_id, p_user_id, p_company_id,
        p_table_schema, p_table_name, p_record_id,
        p_action, p_old_data, p_new_data, p_summary, p_meta
    )
    RETURNING id INTO v_audit_id;

    -- 2. For UPDATEs, explode changed columns into audit_field_change
    IF p_action = 'UPDATE' AND p_old_data IS NOT NULL AND p_new_data IS NOT NULL THEN
        FOR v_key IN
            SELECT key
            FROM jsonb_each_text(p_new_data) AS n(key, val)
            WHERE (p_old_data ->> key) IS DISTINCT FROM (p_new_data ->> key)
        LOOP
            INSERT INTO logs.audit_field_change (
                audit_log_id, field_name, old_value, new_value
            )
            VALUES (
                v_audit_id,
                v_key,
                p_old_data  ->> v_key,
                p_new_data  ->> v_key
            );
        END LOOP;
    END IF;

    RETURN v_audit_id;
END;
$$;