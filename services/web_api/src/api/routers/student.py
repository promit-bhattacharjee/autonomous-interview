import json
import os
from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
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

    from src.api.services import vault_service

    assigned_bank = question_service.get_assigned_bank_for_user(db, current_user.id)
    model_matrix = vault_service.get_student_model_matrix(db, current_user.id)

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
            "model_matrix": model_matrix,
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


@router.post("/credentials")
def update_student_credential(
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Candidate API key capture is disabled. Model engines are managed exclusively by institution administrators.",
    )


@router.post("/credentials/delete")
def delete_student_credential(
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Candidate API key management is disabled. Model engines are managed exclusively by institution administrators.",
    )


@router.post("/byok")
def update_byok_key(
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Candidate API key capture is disabled. Model engines are managed exclusively by institution administrators.",
    )


@router.get("/api/profile")
def get_student_profile_api(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()
    assigned_bank = question_service.get_assigned_bank_for_user(db, current_user.id)
    return {
        "user_id": current_user.id,
        "username": current_user.username,
        "full_name": profile.full_name if profile else current_user.username,
        "academic_background": profile.academic_background if profile else "",
        "english_proficiency": profile.english_proficiency if profile else "",
        "tuition_fee_gbp": profile.tuition_fee_gbp if profile else 0.0,
        "available_funds_gbp": profile.available_funds_gbp if profile else 0.0,
        "sponsor_details": profile.sponsor_details if profile else "",
        "post_study_plan": profile.post_study_plan if profile else "",
        "assigned_bank": assigned_bank,
    }


@router.get("/api/model-config")
def get_student_model_config_api(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from src.api.services import vault_service
    return vault_service.get_student_model_matrix(db, current_user.id)


@router.post("/api/credentials")
def save_student_credential_api(
    payload: Optional[dict] = None,
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Candidate API key capture is disabled. Model engines are managed exclusively by institution administrators.",
    )


@router.delete("/api/credentials/{category}")
def delete_student_credential_api(
    category: str,
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Candidate API key management is disabled. Model engines are managed exclusively by institution administrators.",
    )


@router.get("/interview", response_class=HTMLResponse)
def launch_interview_screen(
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
    if not assigned_bank:
        return RedirectResponse(url="/student?error=pre_assignment_gate", status_code=status.HTTP_303_SEE_OTHER)

    room_name = f"room-{current_user.id}"
    session_record = (
        db.query(InterviewSessionRecord)
        .filter(
            InterviewSessionRecord.student_id == profile.id,
            InterviewSessionRecord.room_name == room_name,
            InterviewSessionRecord.status.in_(["created", "in_progress"]),
        )
        .order_by(InterviewSessionRecord.created_at.desc())
        .first()
    )

    livekit_url = os.getenv("LIVEKIT_URL", "ws://127.0.0.1:7880")

    return get_templates().TemplateResponse(
        request=request,
        name="student/interview.html",
        context={
            "user": current_user,
            "assigned_bank": assigned_bank,
            "room_name": room_name,
            "session_id": session_record.id if session_record else "",
            "livekit_url": livekit_url,
        },
    )


@router.get("/token")
def get_candidate_livekit_token(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()
    if not profile:
        profile = StudentProfile(user_id=current_user.id, full_name=current_user.username)
        db.add(profile)
        db.commit()
        db.refresh(profile)

    # Pre-Assignment Gate check
    assigned_bank = question_service.get_assigned_bank_for_user(db, current_user.id)
    if not assigned_bank:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pre-Assignment Gate: An admissions officer must assign a verified Question Bank before token issuance.",
        )

    room_name = f"room-{current_user.id}"

    # Active session tracker: find existing in_progress session or create new one for this room
    session_record = (
        db.query(InterviewSessionRecord)
        .filter(
            InterviewSessionRecord.student_id == profile.id,
            InterviewSessionRecord.room_name == room_name,
            InterviewSessionRecord.status.in_(["created", "in_progress"]),
        )
        .order_by(InterviewSessionRecord.created_at.desc())
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


@router.post("/discard")
def discard_student_interview_session(
    payload: Optional[dict] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Immediate Student Discard Endpoint:
    Marks active in_progress session as discarded immediately, records elapsed time and turns used,
    purges unconfirmed turn evaluations, and immediately stops background execution.
    """
    from datetime import datetime, timezone
    from src.api.db.models import TurnEvaluationRecord

    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()
    if not profile:
        return {"status": "no_profile"}

    session_record = (
        db.query(InterviewSessionRecord)
        .filter(
            InterviewSessionRecord.student_id == profile.id,
            InterviewSessionRecord.status.in_(["created", "in_progress"]),
        )
        .order_by(InterviewSessionRecord.created_at.desc())
        .first()
    )
    if not session_record:
        return {"status": "no_active_session"}

    now = datetime.now(timezone.utc)
    elapsed_seconds = 0.0
    if session_record.created_at:
        try:
            created_tz = session_record.created_at if session_record.created_at.tzinfo else session_record.created_at.replace(tzinfo=timezone.utc)
            elapsed_seconds = (now - created_tz).total_seconds()
        except Exception:
            pass

    reason = (payload or {}).get("reason", "Candidate explicitly discarded session")
    turns_count = db.query(TurnEvaluationRecord).filter(TurnEvaluationRecord.session_id == session_record.id).count()

    # Purge partial unconfirmed turn evaluation records
    db.query(TurnEvaluationRecord).filter(TurnEvaluationRecord.session_id == session_record.id).delete()

    session_record.status = "discarded"
    session_record.concluded_at = now
    session_record.report_json = json.dumps({
        "status": "discarded",
        "reason": reason,
        "elapsed_seconds": round(elapsed_seconds, 1),
        "turns_used": turns_count,
        "discarded_at": now.isoformat(),
    })
    db.commit()
    return {
        "status": "discarded",
        "session_id": session_record.id,
        "elapsed_seconds": round(elapsed_seconds, 1),
        "turns_used": turns_count,
        "reason": reason,
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
