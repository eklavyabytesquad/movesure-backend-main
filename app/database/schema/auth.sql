-- ============================================================
-- AUTH TABLES
-- auth_sessions, auth_tokens, auth_security_events
-- Depends on: tenant.sql, iam.sql
-- ============================================================


-- ============================================================
-- auth_sessions
-- One row = one logged-in device/browser
-- ============================================================
CREATE TABLE auth_sessions (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID            NOT NULL REFERENCES iam_users(id)                ON DELETE CASCADE,
    company_id      UUID            NOT NULL REFERENCES tenant_companies(company_id)  ON DELETE CASCADE,

    ip_address      INET,
    user_agent      TEXT,
    device_name     VARCHAR(100),
    device_type     VARCHAR(20)     NOT NULL DEFAULT 'web'
                        CHECK (device_type IN ('web', 'mobile', 'api')),

    status          VARCHAR(20)     NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'expired', 'revoked')),
    expires_at      TIMESTAMPTZ     NOT NULL,
    revoked_at      TIMESTAMPTZ,

    last_active_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_auth_sessions_user   ON auth_sessions(user_id);
CREATE INDEX idx_auth_sessions_active ON auth_sessions(user_id, status)
    WHERE status = 'active';


-- ============================================================
-- auth_tokens
-- Access + refresh tokens — SHA-256 hash only, never raw token
-- ============================================================
CREATE TABLE auth_tokens (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID            NOT NULL REFERENCES auth_sessions(id) ON DELETE CASCADE,
    user_id         UUID            NOT NULL REFERENCES iam_users(id)     ON DELETE CASCADE,

    type            VARCHAR(20)     NOT NULL
                        CHECK (type IN (
                            'access',           -- 15 min JWT
                            'refresh',          -- 7-30 days, rotated on use
                            'password_reset',   -- one-time, 1 hour
                            'email_verify'      -- one-time, 24 hours
                        )),

    token_hash      VARCHAR(64)     NOT NULL UNIQUE,  -- SHA-256 of raw token
    expires_at      TIMESTAMPTZ     NOT NULL,
    is_revoked      BOOLEAN         NOT NULL DEFAULT FALSE,
    revoked_at      TIMESTAMPTZ,
    last_used_at    TIMESTAMPTZ,

    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_auth_tokens_hash      ON auth_tokens(token_hash);
CREATE INDEX idx_auth_tokens_session   ON auth_tokens(session_id);
CREATE INDEX idx_auth_tokens_user_type ON auth_tokens(user_id, type)
    WHERE is_revoked = FALSE;


-- ============================================================
-- auth_security_events
-- Append-only log — never update or delete rows
-- ============================================================
CREATE TABLE auth_security_events (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID            REFERENCES iam_users(id)     ON DELETE SET NULL,
    session_id      UUID            REFERENCES auth_sessions(id) ON DELETE SET NULL,

    event_type      VARCHAR(50)     NOT NULL
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
    meta            JSONB           NOT NULL DEFAULT '{}',

    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_auth_sec_events_user    ON auth_security_events(user_id, created_at DESC);
CREATE INDEX idx_auth_sec_events_type    ON auth_security_events(event_type, created_at DESC);
CREATE INDEX idx_auth_sec_events_session ON auth_security_events(session_id);
