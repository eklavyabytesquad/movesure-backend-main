from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.services.tenant.service import create_company, create_branch, get_company_by_email
from app.services.iam.service import create_user, get_user_by_email
from app.services.auth.service import hash_password

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


# ── Request models ────────────────────────────────────────────

class CompanyIn(BaseModel):
    name:         str          = Field(..., min_length=2)
    address:      str | None   = None
    phone_number: str | None   = None
    email:        EmailStr | None = None
    gstin:        str | None   = None
    plan:         str | None   = None


class BranchIn(BaseModel):
    name:        str        = Field(..., min_length=2)
    branch_code: str        = Field(..., min_length=2)
    address:     str | None = None


class AdminIn(BaseModel):
    full_name:      str      = Field(..., min_length=2)
    email:          EmailStr
    password:       str      = Field(..., min_length=8)
    post_in_office: str      = "super_admin"


class OnboardingRequest(BaseModel):
    company: CompanyIn
    branch:  BranchIn
    admin:   AdminIn


# ── Endpoint ──────────────────────────────────────────────────

@router.post("/setup", status_code=201, summary="Onboard a new tenant")
def setup_tenant(body: OnboardingRequest):
    """
    Single-shot onboarding:
    1. Create company
    2. Create primary branch under the company
    3. Create super_admin user linked to both
    """
    # Guard: company email must be unique
    if body.company.email and get_company_by_email(body.company.email):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A company with email '{body.company.email}' already exists.",
        )

    # Guard: admin email must be unique
    if get_user_by_email(body.admin.email):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A user with email '{body.admin.email}' already exists.",
        )

    # Step 1 — Company
    company = create_company(body.company.model_dump(exclude_none=True))

    # Step 2 — Primary branch
    branch = create_branch({
        **body.branch.model_dump(exclude_none=True),
        "company_id":  company["company_id"],
        "branch_type": "primary",
    })

    # Step 3 — Super admin user
    user = create_user({
        "full_name":      body.admin.full_name,
        "email":          body.admin.email,
        "password":       hash_password(body.admin.password),
        "post_in_office": body.admin.post_in_office,
        "company_id":     company["company_id"],
        "branch_id":      branch["branch_id"],
    })
    user.pop("password", None)  # never return the hash

    return {
        "message": "Tenant onboarded successfully. You can now log in.",
        "company": company,
        "branch":  branch,
        "admin":   user,
    }
