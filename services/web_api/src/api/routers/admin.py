from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from src.api.db.models import QuestionBank, StudentProfile, User
from src.api.db.session import get_db
from src.api.security.auth import require_admin
from src.api.services import question_service

router = APIRouter(prefix="/admin", tags=["Admin Portal"])


def get_templates() -> Jinja2Templates:
    from src.api.main import templates
    return templates


@router.get("", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from src.api.services import vault_service

    banks = db.query(QuestionBank).order_by(QuestionBank.created_at.desc()).all()
    students = db.query(StudentProfile).all()
    model_matrix = vault_service.get_admin_model_matrix(db)
    students_byok = vault_service.get_students_byok_overview(db)

    return get_templates().TemplateResponse(
        request=request,
        name="admin/dashboard.html",
        context={
            "user": admin_user,
            "banks": banks,
            "students": students,
            "model_matrix": model_matrix,
            "students_byok": students_byok,
        },
    )


@router.post("/credentials")
def update_admin_credential(
    category: str = Form(...),
    provider: str = Form(...),
    api_key: str = Form(...),
    model_name: str = Form(None),
    base_url: str = Form(None),
    voice: str = Form(None),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if category == "stt" and not (model_name and model_name.strip()):
        prov_clean = provider.strip().lower()
        stt_defaults = {
            "groq": "whisper-large-v3-turbo",
            "openai": "whisper-1",
            "deepgram": "nova-2",
            "google": "gemini-2.0-flash",
        }
        model_name = stt_defaults.get(prov_clean, "whisper-large-v3-turbo")

    if category == "tts" and not (model_name and model_name.strip()):
        prov_clean = provider.strip().lower()
        tts_defaults = {
            "deepgram": "aura-asteria-en",
            "openai": "tts-1",
            "google": "gemini-2.5-flash-preview-tts",
        }
        model_name = tts_defaults.get(prov_clean, "aura-asteria-en")

    from src.api.services import vault_service
    vault_service.save_model_credential(
        db=db,
        category=category,
        provider=provider,
        api_key=api_key,
        model_name=model_name,
        base_url=base_url,
        voice=voice,
        user_id=None,
        is_admin=True,
    )
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/credentials/delete")
def delete_admin_credential(
    category: str = Form(...),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from src.api.services import vault_service
    vault_service.delete_model_credential(
        db=db,
        category=category,
        user_id=None,
        is_admin=True,
    )
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/students/{student_id}/clean-keys")
def clean_student_keys(
    student_id: str,
    category: str = Form(None),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from src.api.services import vault_service
    vault_service.clean_student_credentials(
        db=db,
        student_id=student_id,
        category=category if category and category.strip() else None,
    )
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)



@router.post("/assignments")
def assign_bank(
    student_id: str = Form(...),
    bank_id: str = Form(...),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    question_service.assign_bank_to_student(db, bank_id=bank_id, student_id=student_id)
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/banks", response_class=HTMLResponse)
def list_question_banks(
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    banks = db.query(QuestionBank).order_by(QuestionBank.created_at.desc()).all()

    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse(
            content=[
                {
                    "id": b.id,
                    "title": b.title,
                    "difficulty": b.difficulty.value if hasattr(b.difficulty, "value") else str(b.difficulty),
                    "is_active": b.is_active,
                    "topics_count": len(b.topics) if b.topics else 0,
                    "created_at": b.created_at.isoformat() if b.created_at else None,
                }
                for b in banks
            ]
        )

    return get_templates().TemplateResponse(
        request=request,
        name="admin/banks.html",
        context={
            "user": admin_user,
            "banks": banks,
        },
    )


@router.post("/banks/generate")
def trigger_generation_graph(
    request: Request,
    title: str = Form(...),
    difficulty: str = Form("Medium"),
    curriculum_text: str = Form(...),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # Generates a starter segment set and saves bank
    starter_topics = [
        {
            "name": "General Credibility & Motivation",
            "description": "Why the UK, university choice, and career orientation",
            "questions": [
                {
                    "question_text": f"Explain why you decided to pursue your studies under this specific syllabus: {title}?",
                    "expected_time_to_ans": 45,
                    "expected_answer_keywords": ["curriculum", "accreditation", "career"],
                    "followups": [
                        {
                            "followup_text": "How will the modules covered contribute directly to your career plans upon return?",
                            "expected_time_to_ans": 30,
                            "expected_answer_keywords": ["specialization", "skills", "employment"],
                        }
                    ],
                }
            ],
        }
    ]
    question_service.create_question_bank_from_payload(
        db=db,
        title=title,
        difficulty=difficulty,
        university_id=None,
        topics_payload=starter_topics,
        curriculum_source=curriculum_text,
    )
    referer = request.headers.get("referer", "")
    target_url = "/admin/banks" if "banks" in referer else "/admin"
    return RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/banks/{bank_id}", response_class=HTMLResponse)
def view_bank_tree(
    bank_id: str,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    bank = question_service.get_full_bank_tree(db, bank_id)
    if not bank:
        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

    return get_templates().TemplateResponse(
        request=request,
        name="admin/bank_detail.html",
        context={
            "user": admin_user,
            "bank": bank,
        },
    )


@router.post("/banks/{bank_id}/edit-question")
def edit_question(
    bank_id: str,
    question_id: str = Form(...),
    question_text: str = Form(...),
    expected_time_to_ans: int = Form(45),
    keywords_raw: str = Form(""),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
    question_service.update_question_record(
        db=db,
        question_id=question_id,
        question_text=question_text,
        expected_time_to_ans=expected_time_to_ans,
        expected_answer_keywords=keywords,
    )
    return RedirectResponse(url=f"/admin/banks/{bank_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/banks/{bank_id}/edit-followup")
def edit_followup(
    bank_id: str,
    followup_id: str = Form(...),
    followup_text: str = Form(...),
    expected_time_to_ans: int = Form(30),
    keywords_raw: str = Form(""),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
    question_service.update_followup_record(
        db=db,
        followup_id=followup_id,
        followup_text=followup_text,
        expected_time_to_ans=expected_time_to_ans,
        expected_answer_keywords=keywords,
    )
    return RedirectResponse(url=f"/admin/banks/{bank_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/banks/{bank_id}/add-followup")
def add_followup(
    bank_id: str,
    question_id: str = Form(...),
    followup_text: str = Form(...),
    expected_time_to_ans: int = Form(30),
    keywords_raw: str = Form(""),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
    question_service.add_followup_to_question(
        db=db,
        question_id=question_id,
        followup_text=followup_text,
        expected_time_to_ans=expected_time_to_ans,
        expected_answer_keywords=keywords,
    )
    return RedirectResponse(url=f"/admin/banks/{bank_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/banks/{bank_id}/toggle-active")
def toggle_bank_status(
    bank_id: str,
    request: Request,
    is_active: bool = Form(...),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    question_service.toggle_bank_active(db, bank_id=bank_id, is_active=is_active)
    referer = request.headers.get("referer", "")
    target_url = referer if referer else f"/admin/banks/{bank_id}"
    return RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/evaluations", response_class=HTMLResponse)
def list_evaluations(
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from src.api.db.models import InterviewSessionRecord
    sessions = (
        db.query(InterviewSessionRecord)
        .order_by(InterviewSessionRecord.created_at.desc())
        .all()
    )
    return get_templates().TemplateResponse(
        request=request,
        name="admin/evaluations.html",
        context={
            "user": admin_user,
            "sessions": sessions,
        },
    )
