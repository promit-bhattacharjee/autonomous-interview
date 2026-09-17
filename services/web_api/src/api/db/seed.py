import json
import logging
import sys
from pathlib import Path

# Ensure web_api package is in sys.path when invoked directly
web_api_root = Path(__file__).resolve().parent.parent.parent.parent
if str(web_api_root) not in sys.path:
    sys.path.insert(0, str(web_api_root))

from sqlalchemy.orm import Session
from src.api.db.models import (
    DifficultyTier,
    FollowupRecord,
    QuestionAssignment,
    QuestionBank,
    QuestionRecord,
    StudentProfile,
    TopicRecord,
    University,
    User,
    UserRole,
)
from src.api.db.session import SessionLocal, init_db
from src.api.security.auth import hash_password

logger = logging.getLogger("seed")
logging.basicConfig(level=logging.INFO)


def seed_database(db: Session) -> dict[str, str]:
    """
    Seeds initial admin and student accounts, along with standard university
    curriculum, question bank, topics, questions, follow-ups, and student assignment.
    Idempotent: updates existing accounts/records without duplicating.
    """
    init_db()

    # 1. Seed Admin User (admin / admin)
    admin_user = db.query(User).filter(User.username == "admin").first()
    if not admin_user:
        admin_user = User(
            username="admin",
            email="admin@ukvi-interview.org",
            hashed_password=hash_password("admin"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin_user)
        logger.info("Created admin user: admin / admin")
    else:
        admin_user.hashed_password = hash_password("admin")
        admin_user.role = UserRole.ADMIN
        logger.info("Updated existing admin user password to 'admin'")

    # 2. Seed Student User (student / student)
    student_user = db.query(User).filter(User.username == "student").first()
    if not student_user:
        student_user = User(
            username="student",
            email="student@ukvi-interview.org",
            hashed_password=hash_password("student"),
            role=UserRole.STUDENT,
            is_active=True,
        )
        db.add(student_user)
        logger.info("Created student user: student / student")
    else:
        student_user.hashed_password = hash_password("student")
        student_user.role = UserRole.STUDENT
        logger.info("Updated existing student user password to 'student'")

    db.commit()
    db.refresh(admin_user)
    db.refresh(student_user)

    # 3. Seed Standard Target University
    university = db.query(University).filter(University.university_code == "UK-HERTS-01").first()
    if not university:
        university = University(
            university_code="UK-HERTS-01",
            official_name="University of Hertfordshire",
            campus_location="College Lane, Hatfield, Hertfordshire, AL10 9AB",
            tuition_fee_gbp=16500.0,
            living_cost_guideline_gbp=10228.0,
            target_course="MSc Artificial Intelligence with Advanced Research",
            degree_level="Postgraduate",
            duration_months=12,
            core_modules_json=json.dumps([
                "Artificial Intelligence & Neural Networks",
                "Advanced Computer Vision and Perception",
                "Applied Machine Learning Algorithms",
                "Research Methods and Master's Project",
            ]),
            campus_facilities_json=json.dumps([
                "High Performance Computing & GPU Cluster",
                "24/7 Learning Resources Centre (LRC)",
                "Autonomous Systems & Robotics Laboratory",
            ]),
            competitor_differentiators_json=json.dumps([
                "TEF Gold rated university for teaching excellence",
                "Direct industrial placement opportunities in UK tech triangle",
                "Strong alumni employment track record in AI engineering",
            ]),
            compliance_rubrics_json=json.dumps([
                "UKVI Part 9 Genuine Student Credibility Standard",
                "Strict verification of course choice, module comprehension, and 28-day maintenance funds",
            ]),
        )
        db.add(university)
        db.commit()
        db.refresh(university)
        logger.info("Created standard University record: UK-HERTS-01")

    # 4. Seed / Update Student Profile
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == student_user.id).first()
    if not profile:
        profile = StudentProfile(
            user_id=student_user.id,
            selected_university_id=university.id,
            full_name="Alex Morgan",
            academic_background="BSc (Hons) Computer Science, First Class Honours (3.85 GPA)",
            english_proficiency="IELTS Academic Band 7.5 (L: 8.0, R: 7.5, W: 7.0, S: 7.5)",
            tuition_fee_gbp=16500.0,
            living_cost_gbp=10228.0,
            available_funds_gbp=29500.0,
            sponsor_details="Family sponsored; £29,500 held in fixed savings for > 28 consecutive days in Standard Chartered Bank",
            post_study_plan="Return to home country upon course completion to take up an AI Systems Engineer position in fintech",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        logger.info("Created StudentProfile for student user")
    else:
        profile.selected_university_id = university.id
        profile.full_name = "Alex Morgan"
        db.commit()

    # 5. Seed Comprehensive Question Bank (5 Topics, each with 1 Question and 4 Follow-ups)
    bank = db.query(QuestionBank).filter(QuestionBank.title == "UKVI Academic Credibility & Genuine Student Assessment").first()
    if not bank:
        bank = QuestionBank(
            university_id=university.id,
            title="UKVI Academic Credibility & Genuine Student Assessment",
            difficulty=DifficultyTier.MEDIUM,
            curriculum_source="Official UKVI Credibility Framework + University of Hertfordshire MSc AI Syllabus",
            is_active=True,
        )
        db.add(bank)
        db.commit()
        db.refresh(bank)
    else:
        # Clear existing topics for a clean replacement
        db.query(TopicRecord).filter(TopicRecord.bank_id == bank.id).delete()
        db.commit()

    topics_data = [
        {
            "name": "Academic Intent & Course Choice",
            "description": "Assesses candidate motivation for studying in the UK, university selection rationale, and syllabus comprehension.",
            "order": 1,
            "question": {
                "text": "Why have you chosen to study MSc Artificial Intelligence with Advanced Research at the University of Hertfordshire rather than in your home country?",
                "time": 45,
                "keywords": ["curriculum", "accreditation", "career", "facilities", "hertfordshire", "modules", "teaching excellence"],
                "followups": [
                    {
                        "text": "Which specific modules in this course are most closely aligned with your undergraduate background?",
                        "time": 30,
                        "keywords": ["neural networks", "computer vision", "machine learning", "research methods", "project", "bachelor"],
                    },
                    {
                        "text": "How is the MSc programme structured in terms of credit distribution, coursework assessments, and dissertation requirements?",
                        "time": 30,
                        "keywords": ["credits", "dissertation", "coursework", "exams", "assessment", "thesis", "modules"],
                    },
                    {
                        "text": "What specific academic facilities or research laboratories at the Hatfield campus will you utilize during your studies?",
                        "time": 30,
                        "keywords": ["hpc", "computing lab", "learning resources centre", "robotics", "gpu cluster", "facilities"],
                    },
                    {
                        "text": "Did you consider any other universities in the UK or elsewhere before finalizing Hertfordshire, and what made you choose Hertfordshire?",
                        "time": 30,
                        "keywords": ["rankings", "location", "course content", "tuition", "offers", "decision", "placement"],
                    },
                ],
            },
        },
        {
            "name": "Financial Maintenance & 28-Day Rule",
            "description": "Verifies UKVI financial compliance, maintenance funds calculation, and authentic sponsorship documentation.",
            "order": 2,
            "question": {
                "text": "How are your tuition fees of £16,500 and living expenses being funded, and how do you meet the UKVI 28-day financial requirement?",
                "time": 45,
                "keywords": ["sponsor", "funds", "28 days", "bank deposit", "living costs", "statement", "savings", "maintenance"],
                "followups": [
                    {
                        "text": "What official documentation has your sponsor provided to prove these funds are genuine and readily accessible?",
                        "time": 30,
                        "keywords": ["bank statement", "affidavit", "tax returns", "source of wealth", "salary", "balance"],
                    },
                    {
                        "text": "Under UKVI regulations, how did you satisfy the mandatory 28-day consecutive holding rule for your maintenance funds prior to CAS issuance?",
                        "time": 30,
                        "keywords": ["28 consecutive days", "minimum balance", "statement date", "closing balance", "compliance", "bank"],
                    },
                    {
                        "text": "What is your estimated monthly budget for accommodation, food, utilities, and local transport in the Hatfield area?",
                        "time": 30,
                        "keywords": ["rent", "accommodation", "monthly budget", "food", "transport", "utilities", "living costs"],
                    },
                    {
                        "text": "Are you planning to undertake part-time work during term time, and what are the legal work hour restrictions on a UK Student Visa?",
                        "time": 30,
                        "keywords": ["20 hours per week", "term time", "part-time", "visa restriction", "full-time vacation", "legal limit"],
                    },
                ],
            },
        },
        {
            "name": "Accommodation, Living & Travel Logistics",
            "description": "Assesses realistic living arrangements, geographical familiarity with Hatfield, travel itinerary, and healthcare registration.",
            "order": 3,
            "question": {
                "text": "Where do you intend to live during your course at Hertfordshire, and how far is that accommodation from the College Lane campus?",
                "time": 45,
                "keywords": ["campus accommodation", "halls of residence", "hatfield", "college lane", "walking distance", "commute"],
                "followups": [
                    {
                        "text": "Have you already applied for on-campus halls or private rented housing, and what is the expected weekly or monthly rental cost?",
                        "time": 30,
                        "keywords": ["deposit", "tenancy agreement", "weekly rent", "student halls", "contract", "rent"],
                    },
                    {
                        "text": "What is your planned travel route from the arrival airport in the UK to your residence in Hatfield?",
                        "time": 30,
                        "keywords": ["heathrow", "luton", "train", "express bus", "airport pickup", "travel", "london"],
                    },
                    {
                        "text": "How do you plan to register with a local National Health Service (NHS) General Practitioner (GP) surgery once you arrive?",
                        "time": 30,
                        "keywords": ["nhs", "ihs surcharge", "gp surgery", "medical centre", "health registration", "clinic"],
                    },
                    {
                        "text": "Do you have any family members, dependants, or relatives currently residing in the United Kingdom?",
                        "time": 30,
                        "keywords": ["dependants", "family", "relatives", "independent living", "ukvi declaration", "no relatives"],
                    },
                ],
            },
        },
        {
            "name": "Post-Study Career Trajectory & ROI",
            "description": "Evaluates candidate genuine return intent, future job market alignment, and credibility of return on educational investment.",
            "order": 4,
            "question": {
                "text": "What are your specific post-graduation career plans, and how will returning to your home country provide a return on your educational investment?",
                "time": 45,
                "keywords": ["return", "home country", "career", "salary", "machine learning engineer", "investment", "roi", "fintech"],
                "followups": [
                    {
                        "text": "What specific job roles, industries, and target companies will you be applying to in your home country after graduating?",
                        "time": 30,
                        "keywords": ["machine learning engineer", "ai developer", "fintech", "companies", "data scientist", "tech industry"],
                    },
                    {
                        "text": "What is the anticipated starting salary for someone with this UK postgraduate qualification compared to a local graduate in your country?",
                        "time": 30,
                        "keywords": ["starting salary", "remuneration", "compensation", "higher income", "market rate", "benchmark"],
                    },
                    {
                        "text": "How will the specialized skills gained from this AI course give you a competitive advantage in your home country's job market?",
                        "time": 30,
                        "keywords": ["competitive edge", "advanced research", "practical skills", "deep learning", "market demand"],
                    },
                    {
                        "text": "Are you aware of the UK Graduate Visa route, and what factors will guide your decision on whether to apply for post-study work or return immediately?",
                        "time": 30,
                        "keywords": ["graduate visa", "post-study work", "2 years", "experience", "return home", "career growth"],
                    },
                ],
            },
        },
        {
            "name": "Immigration Compliance & Visa Regulations",
            "description": "Tests awareness of UK student visa conditions, attendance monitoring compliance, and authentic applicant declarations.",
            "order": 5,
            "question": {
                "text": "Do you have any previous visa refusals, entry curtailments, or overstay history for the United Kingdom or any other country?",
                "time": 45,
                "keywords": ["refusal", "history", "clear record", "compliance", "previous visas", "travel history", "no refusal"],
                "followups": [
                    {
                        "text": "What are your core legal responsibilities and visa conditions as a sponsored international student studying in the UK?",
                        "time": 30,
                        "keywords": ["attendance", "biometric residence permit", "brp", "academic progress", "conditions", "compliance"],
                    },
                    {
                        "text": "What does the university's UKVI compliance team require regarding lecture attendance monitoring and unauthorized absences?",
                        "time": 30,
                        "keywords": ["attendance monitoring", "check-in", "unauthorized absence", "cas curtailment", "reporting", "registers"],
                    },
                    {
                        "text": "What steps must you take if your passport, biometric residence permit, or visa documentation is lost or stolen while residing in the UK?",
                        "time": 30,
                        "keywords": ["home office", "police report", "international student support", "replacement brp", "report"],
                    },
                    {
                        "text": "Can you confirm that all information, academic transcripts, and financial records submitted with your visa application are authentic and unmodified?",
                        "time": 30,
                        "keywords": ["authentic", "genuine", "certified transcripts", "truthful", "unmodified", "declaration"],
                    },
                ],
            },
        },
    ]

    for topic_info in topics_data:
        topic = TopicRecord(
            bank_id=bank.id,
            name=topic_info["name"],
            description=topic_info["description"],
            order=topic_info["order"],
        )
        db.add(topic)
        db.commit()
        db.refresh(topic)

        q_info = topic_info["question"]
        q_record = QuestionRecord(
            topic_id=topic.id,
            question_text=q_info["text"],
            expected_time_to_ans=q_info["time"],
            expected_answer_keywords_json=json.dumps(q_info["keywords"]),
            order=1,
        )
        db.add(q_record)
        db.commit()
        db.refresh(q_record)

        for f_idx, f_info in enumerate(q_info["followups"], start=1):
            f_record = FollowupRecord(
                question_id=q_record.id,
                followup_text=f_info["text"],
                expected_time_to_ans=f_info["time"],
                expected_answer_keywords_json=json.dumps(f_info["keywords"]),
                order=f_idx,
            )
            db.add(f_record)

        db.commit()

    logger.info("Successfully seeded 5 Topics, each with 1 Question and 4 Follow-up probes (20 total follow-ups).")

    # 6. Assign Question Bank to Student (Pre-Assignment Gate fulfillment)
    existing_assignment = (
        db.query(QuestionAssignment)
        .filter(
            QuestionAssignment.bank_id == bank.id,
            QuestionAssignment.student_id == profile.id,
        )
        .first()
    )
    if not existing_assignment:
        assignment = QuestionAssignment(
            bank_id=bank.id,
            student_id=profile.id,
            is_excluded=False,
        )
        db.add(assignment)
        logger.info("Assigned question bank directly to student profile")

    # Also ensure a global assignment exists
    global_assignment = (
        db.query(QuestionAssignment)
        .filter(
            QuestionAssignment.bank_id == bank.id,
            QuestionAssignment.student_id == None,
        )
        .first()
    )
    if not global_assignment:
        global_assignment = QuestionAssignment(
            bank_id=bank.id,
            student_id=None,
            is_excluded=False,
        )
        db.add(global_assignment)
        logger.info("Created global fallback question bank assignment")

    # 7. Seed Admin-Managed AI Engines (Thinking, STT, TTS) and Purge Candidate Keys
    from src.api.db.models import CredentialVault
    from src.api.services import vault_service

    # Purge any candidate-side keys from the database (Strict Admin-Only Custody)
    db.query(CredentialVault).filter(CredentialVault.is_admin_key == False).delete(synchronize_session=False)

    # 1. Admin DeepSeek Thinking Credential (via OpenRouter)
    import os
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "sk-or-v1-placeholder-seed-key-for-local-development")
    vault_service.save_model_credential(
        db=db,
        category="thinking",
        provider="openrouter",
        api_key=openrouter_key,
        model_name="deepseek/deepseek-chat",
        base_url="https://openrouter.ai/api/v1",
        user_id=None,
        is_admin=True,
    )
    logger.info("Seeded Admin Thinking Engine: deepseek/deepseek-chat via OpenRouter")

    # 2. Admin Groq Whisper Speech-to-Text (STT) Credential
    groq_key = "gsk_candidate_groq_whisper_ultra_fast_stt_key_2026"
    vault_service.save_model_credential(
        db=db,
        category="stt",
        provider="groq",
        api_key=groq_key,
        model_name="whisper-large-v3-turbo",
        user_id=None,
        is_admin=True,
    )
    logger.info("Seeded Admin Groq Whisper STT: whisper-large-v3-turbo")

    # 3. Admin Text-to-Speech (TTS) Credential: Deepgram Aura ($0.015/1k chars, low latency)
    deepgram_key = "dg_candidate_deepgram_aura_lowest_cost_tts_key_2026"
    vault_service.save_model_credential(
        db=db,
        category="tts",
        provider="deepgram",
        api_key=deepgram_key,
        model_name="aura-asteria-en",
        voice="Asteria",
        user_id=None,
        is_admin=True,
    )
    logger.info("Seeded Admin Deepgram Aura TTS: aura-asteria-en (Asteria Voice, $0.015/1k chars)")

    db.commit()
    logger.info("Database seeding completed successfully.")

    return {
        "admin_username": "admin",
        "admin_password": "admin",
        "student_username": "student",
        "student_password": "student",
        "student_name": profile.full_name,
        "bank_title": bank.title,
        "institution_thinking": "DeepSeek (deepseek/deepseek-chat via OpenRouter)",
        "institution_stt": "Groq Whisper (whisper-large-v3-turbo)",
        "institution_tts": "Deepgram Aura (aura-asteria-en - $0.015/1k chars, Lowest Cost & Accurate)",
        "candidate_key_capture": "DISABLED (Admin-Only Custody)",
    }




if __name__ == "__main__":
    session = SessionLocal()
    try:
        res = seed_database(session)
        print("Seeding Result:", json.dumps(res, indent=2))
    finally:
        session.close()
