-- ============================================================
-- FLEET MODULE — Full Schema
-- fleet, fleet_staff
--
-- fleet      : Company-scoped vehicle registry with full document
--              tracking (RC, insurance, permit, fitness, PUC).
-- fleet_staff: Company-scoped driver / owner / conductor registry.
--
-- Challans and Trip Sheets FK into these tables via:
--   fleet_id, driver_id, owner_id, conductor_id
-- vehicle_info JSONB is kept as a snapshot at dispatch time.
--
-- Depends on: tenant.sql, iam.sql
-- Loaded before: challan.sql
-- ============================================================


-- ============================================================
-- fleet_staff
-- ============================================================
-- People associated with fleet operations: owner, driver,
-- conductor, cleaner, mechanic.
-- Defined BEFORE fleet so fleet can FK to fleet_staff.
-- ============================================================
CREATE TABLE fleet_staff (
    staff_id                UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Scope — company-wide staff registry; branch is optional
    company_id              UUID            NOT NULL
                                REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id               UUID
                                REFERENCES tenant_branches(branch_id) ON DELETE SET NULL,

    -- Identity
    name                    VARCHAR(100)    NOT NULL,
    role                    VARCHAR(20)     NOT NULL
                                CHECK (role IN (
                                    'OWNER',        -- vehicle owner / fleet operator
                                    'DRIVER',       -- primary driver
                                    'CONDUCTOR',    -- cleaner / helper / conductor
                                    'CLEANER',      -- cleaner
                                    'MECHANIC'      -- in-house mechanic
                                )),

    -- Contact
    mobile                  VARCHAR(15),
    alternate_mobile        VARCHAR(15),
    email                   VARCHAR(150),
    address                 TEXT,

    -- Government IDs
    aadhar_no               VARCHAR(20),
    pan_no                  VARCHAR(10),

    -- Driving license (relevant for DRIVER role)
    license_no              VARCHAR(30),
    license_expiry          DATE,
    license_type            VARCHAR(10)
                                CHECK (license_type IS NULL OR license_type IN ('LMV', 'HMV', 'BOTH')),

    -- Badge / employee number
    badge_no                VARCHAR(30),

    -- Personal details
    date_of_birth           DATE,
    date_of_joining         DATE,

    -- Emergency contact
    emergency_contact_name  VARCHAR(100),
    emergency_contact_mobile VARCHAR(15),

    -- Bank details (for payments / settlements)
    bank_account_no         VARCHAR(30),
    bank_ifsc               VARCHAR(15),
    bank_name               VARCHAR(100),

    -- Photo
    profile_photo_url       TEXT,

    notes                   TEXT,
    metadata                JSONB           NOT NULL DEFAULT '{}',
    is_active               BOOLEAN         NOT NULL DEFAULT TRUE,

    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL
);

CREATE INDEX idx_fleet_staff_company  ON fleet_staff(company_id);
CREATE INDEX idx_fleet_staff_branch   ON fleet_staff(company_id, branch_id);
CREATE INDEX idx_fleet_staff_role     ON fleet_staff(company_id, role);
CREATE INDEX idx_fleet_staff_mobile   ON fleet_staff(mobile) WHERE mobile IS NOT NULL;
CREATE INDEX idx_fleet_staff_license  ON fleet_staff(license_no) WHERE license_no IS NOT NULL;
CREATE INDEX idx_fleet_staff_active   ON fleet_staff(company_id, is_active) WHERE is_active = TRUE;

-- Alert when license/documents expire
CREATE INDEX idx_fleet_staff_license_expiry ON fleet_staff(license_expiry)
    WHERE license_expiry IS NOT NULL AND is_active = TRUE;

CREATE TRIGGER trg_fleet_staff_updated_at
    BEFORE UPDATE ON fleet_staff
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- fleet
-- ============================================================
-- One row per vehicle. Company-scoped asset registry.
-- Tracks all statutory documents (RC, insurance, permit, fitness, PUC).
-- current_driver_id / current_owner_id / current_conductor_id are
-- convenience FKs for the currently assigned staff members.
-- ============================================================
CREATE TABLE fleet (
    fleet_id                UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Scope — company-wide asset; branch is optional (NULL = all branches)
    company_id              UUID            NOT NULL
                                REFERENCES tenant_companies(company_id) ON DELETE CASCADE,
    branch_id               UUID
                                REFERENCES tenant_branches(branch_id) ON DELETE SET NULL,

    -- Vehicle identity
    vehicle_no              VARCHAR(20)     NOT NULL,   -- e.g. "MH04AB1234"
    vehicle_type            VARCHAR(20)     NOT NULL DEFAULT 'TRUCK'
                                CHECK (vehicle_type IN (
                                    'TRUCK',
                                    'TRAILER',
                                    'MINI_TRUCK',
                                    'PICKUP',
                                    'TANKER',
                                    'OTHER'
                                )),
    make                    VARCHAR(100),               -- manufacturer e.g. "TATA"
    model                   VARCHAR(100),               -- model e.g. "407", "1109"
    year_of_manufacture     INTEGER         CHECK (year_of_manufacture > 1900),
    body_type               VARCHAR(20)
                                CHECK (body_type IS NULL OR body_type IN (
                                    'OPEN', 'CLOSED', 'CONTAINER', 'FLATBED', 'TANKER', 'OTHER'
                                )),
    capacity_kg             NUMERIC         CHECK (capacity_kg IS NULL OR capacity_kg > 0),
    color                   VARCHAR(50),

    -- Chassis & Engine
    engine_no               VARCHAR(50),
    chassis_no              VARCHAR(50),

    -- ── Statutory Documents ─────────────────────────────────

    -- RC (Registration Certificate)
    rc_no                   VARCHAR(50),
    rc_expiry               DATE,

    -- Insurance
    insurance_no            VARCHAR(50),
    insurance_company       VARCHAR(100),
    insurance_expiry        DATE,

    -- Permit
    permit_no               VARCHAR(50),
    permit_type             VARCHAR(20)
                                CHECK (permit_type IS NULL OR permit_type IN (
                                    'NATIONAL', 'STATE', 'LOCAL'
                                )),
    permit_expiry           DATE,

    -- Fitness Certificate
    fitness_no              VARCHAR(50),
    fitness_expiry          DATE,

    -- PUC (Pollution Under Control)
    puc_no                  VARCHAR(50),
    puc_expiry              DATE,

    -- ── Currently Assigned Staff ─────────────────────────────
    -- Convenience pointers — updated via /assign endpoints.
    -- Challans snapshot these at creation time.
    current_owner_id        UUID            REFERENCES fleet_staff(staff_id) ON DELETE SET NULL,
    current_driver_id       UUID            REFERENCES fleet_staff(staff_id) ON DELETE SET NULL,
    current_conductor_id    UUID            REFERENCES fleet_staff(staff_id) ON DELETE SET NULL,

    -- ── Status ───────────────────────────────────────────────
    status                  VARCHAR(20)     NOT NULL DEFAULT 'ACTIVE'
                                CHECK (status IN (
                                    'ACTIVE',       -- available for assignment
                                    'IN_TRANSIT',   -- currently on a trip
                                    'MAINTENANCE',  -- under repair / service
                                    'INACTIVE'      -- retired / sold
                                )),

    notes                   TEXT,
    metadata                JSONB           NOT NULL DEFAULT '{}',
    is_active               BOOLEAN         NOT NULL DEFAULT TRUE,

    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,
    updated_by              UUID            REFERENCES iam_users(id) ON DELETE SET NULL,

    -- Vehicle number must be unique within a company
    CONSTRAINT uq_fleet_vehicle_no UNIQUE (company_id, vehicle_no)
);

CREATE INDEX idx_fleet_company          ON fleet(company_id);
CREATE INDEX idx_fleet_branch           ON fleet(company_id, branch_id);
CREATE INDEX idx_fleet_vehicle_no       ON fleet(vehicle_no);
CREATE INDEX idx_fleet_status           ON fleet(company_id, status);
CREATE INDEX idx_fleet_type             ON fleet(company_id, vehicle_type);
CREATE INDEX idx_fleet_driver           ON fleet(current_driver_id) WHERE current_driver_id IS NOT NULL;
CREATE INDEX idx_fleet_owner            ON fleet(current_owner_id)  WHERE current_owner_id IS NOT NULL;
CREATE INDEX idx_fleet_active           ON fleet(company_id, is_active) WHERE is_active = TRUE;

-- Expiry alert indexes
CREATE INDEX idx_fleet_rc_expiry          ON fleet(rc_expiry)          WHERE rc_expiry IS NOT NULL;
CREATE INDEX idx_fleet_insurance_expiry   ON fleet(insurance_expiry)   WHERE insurance_expiry IS NOT NULL;
CREATE INDEX idx_fleet_permit_expiry      ON fleet(permit_expiry)      WHERE permit_expiry IS NOT NULL;
CREATE INDEX idx_fleet_fitness_expiry     ON fleet(fitness_expiry)     WHERE fitness_expiry IS NOT NULL;
CREATE INDEX idx_fleet_puc_expiry         ON fleet(puc_expiry)         WHERE puc_expiry IS NOT NULL;

CREATE TRIGGER trg_fleet_updated_at
    BEFORE UPDATE ON fleet
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
