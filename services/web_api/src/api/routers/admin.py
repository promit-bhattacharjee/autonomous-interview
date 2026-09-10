from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
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
    banks = db.query(QuestionBank).order_by(QuestionBank.created_at.desc()).all()
    students = db.query(StudentProfile).all()
    return get_templates().TemplateResponse(
        request=request,
        name="admin/dashboard.html",
        context={
            "user": admin_user,
            "banks": banks,
            "students": students,
        },
    )


@router.post("/assignments")
def assign_bank(
    student_id: str = Form(...),
    bank_id: str = Form(...),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    question_service.assign_bank_to_student(db, bank_id=bank_id, student_id=student_id)
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/banks/generate")
def trigger_generation_graph(
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
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


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
    is_active: bool = Form(...),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    question_service.toggle_bank_active(db, bank_id=bank_id, is_active=is_active)
    return RedirectResponse(url=f"/admin/banks/{bank_id}", status_code=status.HTTP_303_SEE_OTHER)


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
