from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from src.api.db.models import AIProvider, CredentialVault, StudentProfile, User
from src.api.db.session import get_db
from src.api.security.auth import get_current_user
from src.api.security.vault import encrypt_api_key, mask_api_key
from src.api.services import question_service

router = APIRouter(prefix="/student", tags=["Student Portal"])


def get_templates() -> Jinja2Templates:
    from src.api.main import templates
    return templates


@router.get("", response_class=HTMLResponse)
def student_dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()
    if not profile:
        profile = StudentProfile(user_id=current_user.id, full_name=current_user.username)
        db.add(profile)
        db.commit()
        db.refresh(profile)

    assigned_bank = question_service.get_assigned_bank_for_user(db, current_user.id)

    # Check for existing BYOK key preview
    vault_entry = db.query(CredentialVault).filter(CredentialVault.user_id == current_user.id).first()
    key_preview = vault_entry.key_preview if vault_entry else None

    return get_templates().TemplateResponse(
        request=request,
        name="student/dashboard.html",
        context={
            "user": current_user,
            "profile": profile,
            "assigned_bank": assigned_bank,
            "current_key_preview": key_preview,
        },
    )


@router.post("/profile")
def update_cas_profile(
    full_name: str = Form(...),
    academic_background: str = Form(...),
    tuition_fee_gbp: float = Form(0.0),
    available_funds_gbp: float = Form(0.0),
    sponsor_details: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()
    if profile:
        profile.full_name = full_name
        profile.academic_background = academic_background
        profile.tuition_fee_gbp = tuition_fee_gbp
        profile.available_funds_gbp = available_funds_gbp
        profile.sponsor_details = sponsor_details
        db.commit()

    return RedirectResponse(url="/student", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/byok")
def update_byok_key(
    provider: str = Form(...),
    api_key: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    encrypted = encrypt_api_key(api_key.strip())
    preview = mask_api_key(api_key.strip())

    entry = db.query(CredentialVault).filter(CredentialVault.user_id == current_user.id).first()
    if entry:
        entry.provider = AIProvider(provider)
        entry.encrypted_api_key = encrypted
        entry.key_preview = preview
    else:
        entry = CredentialVault(
            user_id=current_user.id,
            provider=AIProvider(provider),
            encrypted_api_key=encrypted,
            key_preview=preview,
            is_admin_key=False,
        )
        db.add(entry)

    db.commit()
    return RedirectResponse(url="/student", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/interview")
def launch_interview_gate(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Pre-Assignment Gate check
    assigned_bank = question_service.get_assigned_bank_for_user(db, current_user.id)
    if not assigned_bank:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pre-Assignment Gate: An admissions officer must assign a verified Question Bank before the interview can start.",
        )

    # Return session readiness payload (ready for LiveKit WebRTC connection)
    return {
        "status": "ready",
        "user_id": current_user.id,
        "bank_id": assigned_bank["bank_id"],
        "difficulty": assigned_bank["difficulty"],
        "topics_count": len(assigned_bank["topics"]),
        "message": "Candidate verified and authorized for WebRTC room join.",
    }
