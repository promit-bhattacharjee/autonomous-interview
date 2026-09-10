import json
import os
from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from livekit import api
from sqlalchemy.orm import Session
from src.api.db.models import (
    AIProvider,
    CredentialVault,
    InterviewSessionRecord,
    StudentProfile,
    User,
)
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

    # Check for latest completed session
    latest_session = (
        db.query(InterviewSessionRecord)
        .filter(
            InterviewSessionRecord.student_id == profile.id,
            InterviewSessionRecord.status == "completed",
        )
        .order_by(InterviewSessionRecord.concluded_at.desc())
        .first()
    )

    return get_templates().TemplateResponse(
        request=request,
        name="student/dashboard.html",
        context={
            "user": current_user,
            "profile": profile,
            "assigned_bank": assigned_bank,
            "current_key_preview": key_preview,
            "latest_session": latest_session,
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


@router.get("/interview", response_class=HTMLResponse)
def launch_interview_screen(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assigned_bank = question_service.get_assigned_bank_for_user(db, current_user.id)
    if not assigned_bank:
        return RedirectResponse(url="/student?error=pre_assignment_gate", status_code=status.HTTP_303_SEE_OTHER)

    room_name = f"room-{current_user.id}"
    livekit_url = os.getenv("LIVEKIT_URL", "ws://127.0.0.1:7880")

    return get_templates().TemplateResponse(
        request=request,
        name="student/interview.html",
        context={
            "user": current_user,
            "assigned_bank": assigned_bank,
            "room_name": room_name,
            "livekit_url": livekit_url,
        },
    )


@router.get("/token")
def get_candidate_livekit_token(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Pre-Assignment Gate check
    assigned_bank = question_service.get_assigned_bank_for_user(db, current_user.id)
    if not assigned_bank:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pre-Assignment Gate: An admissions officer must assign a verified Question Bank before token issuance.",
        )

    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()
    if not profile:
        profile = StudentProfile(user_id=current_user.id, full_name=current_user.username)
        db.add(profile)
        db.commit()
        db.refresh(profile)

    room_name = f"room-{current_user.id}"

    # Active session tracker
    session_record = (
        db.query(InterviewSessionRecord)
        .filter(
            InterviewSessionRecord.student_id == profile.id,
            InterviewSessionRecord.room_name == room_name,
            InterviewSessionRecord.status.in_(["created", "in_progress"]),
        )
        .first()
    )
    if not session_record:
        session_record = InterviewSessionRecord(
            student_id=profile.id,
            bank_id=assigned_bank["bank_id"],
            room_name=room_name,
            status="in_progress",
        )
        db.add(session_record)
        db.commit()
        db.refresh(session_record)

    api_key = os.getenv("LIVEKIT_API_KEY", "devkey")
    api_secret = os.getenv("LIVEKIT_API_SECRET", "secret")
    livekit_url = os.getenv("LIVEKIT_URL", "ws://127.0.0.1:7880")

    token = (
        api.AccessToken(api_key, api_secret)
        .with_identity(current_user.id)
        .with_name(profile.full_name or current_user.username)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_publish_sources=["microphone"],
                can_subscribe=True,
                can_publish_data=True,
            )
        )
    )

    return {
        "token": token.to_jwt(),
        "livekit_url": livekit_url,
        "room_name": room_name,
        "session_id": session_record.id,
        "user_id": current_user.id,
        "bank_title": assigned_bank["title"],
        "difficulty": assigned_bank["difficulty"],
        "topics_count": len(assigned_bank.get("topics", [])),
    }


@router.get("/results", response_class=HTMLResponse)
@router.get("/results/{session_id}", response_class=HTMLResponse)
def view_credibility_report(
    request: Request,
    session_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()
    if not profile:
        return RedirectResponse(url="/student", status_code=status.HTTP_303_SEE_OTHER)

    query = db.query(InterviewSessionRecord).filter(
        InterviewSessionRecord.student_id == profile.id,
        InterviewSessionRecord.status == "completed",
    )
    if session_id:
        session_record = query.filter(InterviewSessionRecord.id == session_id).first()
    else:
        session_record = query.order_by(InterviewSessionRecord.concluded_at.desc()).first()

    report = json.loads(session_record.report_json) if session_record and session_record.report_json else None
    turns = session_record.turn_evaluations if session_record else []

    return get_templates().TemplateResponse(
        request=request,
        name="student/results.html",
        context={
            "user": current_user,
            "profile": profile,
            "session": session_record,
            "report": report,
            "turns": turns,
        },
    )
