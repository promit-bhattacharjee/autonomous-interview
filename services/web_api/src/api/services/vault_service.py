import os
from typing import Any, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from src.api.db.models import CredentialVault, ModelCategory
from src.api.security.vault import decrypt_api_key, encrypt_api_key, mask_api_key


VALID_CATEGORIES = [ModelCategory.THINKING.value, ModelCategory.STT.value, ModelCategory.TTS.value]


def get_default_env_config(category: str) -> dict[str, Any]:
    """Resolves default configuration from environment (.env) for a category."""
    if category == ModelCategory.THINKING.value:
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        if openrouter_key:
            provider = "openrouter"
            key = openrouter_key
            model = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash-0731")
            base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        elif google_key:
            provider = "google"
            key = google_key
            model = "gemini-3.6-flash"
            base_url = None
        elif openai_key:
            provider = "openai"
            key = openai_key
            model = "gpt-4o"
            base_url = None
        else:
            provider = "openrouter"
            key = ""
            model = "deepseek/deepseek-v4-flash-0731"
            base_url = "https://openrouter.ai/api/v1"

        return {
            "category": category,
            "provider": provider,
            "model_name": model,
            "base_url": base_url,
            "voice": None,
            "api_key": key,
            "key_preview": mask_api_key(key) if key else "Not Configured",
            "source": "env_fallback",
            "is_free": True,
            "label": "System Default (.env)",
        }

    elif category == ModelCategory.STT.value:
        google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        if google_key:
            provider = "google"
            key = google_key
            model = "gemini-3.6-flash"
        elif openai_key:
            provider = "openai"
            key = openai_key
            model = "whisper-1"
        else:
            provider = "google"
            key = ""
            model = "gemini-3.6-flash"

        return {
            "category": category,
            "provider": provider,
            "model_name": model,
            "base_url": None,
            "voice": None,
            "api_key": key,
            "key_preview": mask_api_key(key) if key else "Not Configured",
            "source": "env_fallback",
            "is_free": True,
            "label": "System Default (.env)",
        }

    elif category == ModelCategory.TTS.value:
        google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        if google_key:
            provider = "google"
            key = google_key
            model = "gemini-2.5-flash-preview-tts"
            voice = "Aoede"
        elif openai_key:
            provider = "openai"
            key = openai_key
            model = "tts-1"
            voice = "alloy"
        else:
            provider = "google"
            key = ""
            model = "gemini-2.5-flash-preview-tts"
            voice = "Aoede"

        return {
            "category": category,
            "provider": provider,
            "model_name": model,
            "base_url": None,
            "voice": voice,
            "api_key": key,
            "key_preview": mask_api_key(key) if key else "Not Configured",
            "source": "env_fallback",
            "is_free": True,
            "label": "System Default (.env)",
        }

    return {
        "category": category,
        "provider": "unknown",
        "model_name": None,
        "base_url": None,
        "voice": None,
        "api_key": "",
        "key_preview": "Not Configured",
        "source": "env_fallback",
        "is_free": True,
        "label": "System Default (.env)",
    }


def has_admin_credential(db: Session, category: str) -> bool:
    """Checks whether an institution/admin key is configured for this category."""
    entry = (
        db.query(CredentialVault)
        .filter(
            CredentialVault.is_admin_key == True,
            CredentialVault.category == category,
        )
        .first()
    )
    return entry is not None and bool(entry.encrypted_api_key)


def save_model_credential(
    db: Session,
    category: str,
    provider: str,
    api_key: str,
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    voice: Optional[str] = None,
    user_id: Optional[str] = None,
    is_admin: bool = False,
) -> CredentialVault:
    """
    Encrypts and upserts an API key and model configuration into CredentialVault.
    If is_admin is True, saves as an Admin/Institution default key.
    If is_admin is False (Student BYOK):
      Enforces the institutional policy rule: if an Admin API key is already provided for this
      category, students cannot modify or override the API key.
    """
    if category not in VALID_CATEGORIES:
        category = ModelCategory.THINKING.value

    # Institutional Policy Rule: Only administrators can configure or modify API keys.
    # Candidate API key capture is completely disabled.
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Candidate API key capture is disabled. Model engines are configured strictly by institution administrators.",
        )

    clean_key = api_key.strip()
    encrypted = encrypt_api_key(clean_key)
    preview = mask_api_key(clean_key)

    query = db.query(CredentialVault).filter(CredentialVault.category == category)
    if is_admin:
        entry = query.filter(CredentialVault.is_admin_key == True).first()
    else:
        entry = query.filter(
            CredentialVault.user_id == user_id,
            CredentialVault.is_admin_key == False,
        ).first()

    if entry:
        entry.provider = provider.strip().lower()
        entry.model_name = (model_name or "").strip() or None
        entry.base_url = (base_url or "").strip() or None
        entry.voice = (voice or "").strip() or None
        entry.encrypted_api_key = encrypted
        entry.key_preview = preview
    else:
        entry = CredentialVault(
            user_id=user_id if not is_admin else None,
            category=category,
            provider=provider.strip().lower(),
            model_name=(model_name or "").strip() or None,
            base_url=(base_url or "").strip() or None,
            voice=(voice or "").strip() or None,
            encrypted_api_key=encrypted,
            key_preview=preview,
            is_admin_key=is_admin,
        )
        db.add(entry)

    db.commit()
    db.refresh(entry)
    return entry


def delete_model_credential(
    db: Session,
    category: str,
    user_id: Optional[str] = None,
    is_admin: bool = False,
) -> bool:
    """Deletes an admin credential from the vault, allowing fallback to .env."""
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Candidate API key management is disabled. Model engines are configured strictly by institution administrators.",
        )

    query = db.query(CredentialVault).filter(CredentialVault.category == category)
    if is_admin:
        entry = query.filter(CredentialVault.is_admin_key == True).first()
    else:
        entry = query.filter(
            CredentialVault.user_id == user_id,
            CredentialVault.is_admin_key == False,
        ).first()

    if entry:
        db.delete(entry)
        db.commit()
        return True
    return False


def clean_student_credentials(
    db: Session,
    student_id: str,
    category: Optional[str] = None,
) -> int:
    """
    Cleans/revokes candidate-configured BYOK credentials from CredentialVault.
    student_id can be a StudentProfile.id or User.id.
    """
    from src.api.db.models import StudentProfile, User
    user = db.query(User).filter(User.id == student_id).first()
    if not user:
        profile = db.query(StudentProfile).filter(StudentProfile.id == student_id).first()
        if profile:
            user = db.query(User).filter(User.id == profile.user_id).first()

    if not user:
        return 0

    query = db.query(CredentialVault).filter(
        CredentialVault.user_id == user.id,
        CredentialVault.is_admin_key == False,
    )
    if category:
        query = query.filter(CredentialVault.category == category)

    deleted_count = query.delete(synchronize_session=False)
    db.commit()
    return deleted_count


def get_students_byok_overview(db: Session) -> list[dict[str, Any]]:
    """
    Returns candidate list with their BYOK key status for Admin dashboard audit and cleaning.
    """
    from src.api.db.models import StudentProfile
    profiles = db.query(StudentProfile).all()
    overview = []
    for p in profiles:
        student_keys = db.query(CredentialVault).filter(
            CredentialVault.user_id == p.user_id,
            CredentialVault.is_admin_key == False,
        ).all()
        categories_set = [k.category for k in student_keys]
        overview.append({
            "student_id": p.id,
            "user_id": p.user_id,
            "full_name": p.full_name,
            "username": p.user.username if p.user else "Unknown",
            "email": p.user.email if p.user else "",
            "byok_count": len(student_keys),
            "byok_categories": categories_set,
            "has_thinking": "thinking" in categories_set,
            "has_stt": "stt" in categories_set,
            "has_tts": "tts" in categories_set,
        })
    return overview


def resolve_model_config(
    db: Session,
    category: str,
    student_user_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Resolves the active model configuration and decrypted key using the institutional governance hierarchy:
    Tier 1 (Governing): Admin Institution Key (if configured, enforces institutional policy & locks student)
    Tier 2: Student BYOK (if no admin key is provided, student BYOK is used)
    Tier 3: Environment Fallback (.env)
    """
    # Tier 1: Check Admin Institution Key first
    admin_entry = (
        db.query(CredentialVault)
        .filter(
            CredentialVault.is_admin_key == True,
            CredentialVault.category == category,
        )
        .first()
    )
    if admin_entry and admin_entry.encrypted_api_key:
        try:
            decrypted = decrypt_api_key(admin_entry.encrypted_api_key)
            return {
                "category": category,
                "provider": admin_entry.provider,
                "model_name": admin_entry.model_name,
                "base_url": admin_entry.base_url,
                "voice": admin_entry.voice,
                "api_key": decrypted,
                "key_preview": admin_entry.key_preview,
                "source": "admin_provided",
                "is_free": False,
                "label": "Institution Default Key",
            }
        except Exception:
            pass

    # Tier 2: If no Admin key is configured, check Student BYOK
    if student_user_id:
        from src.api.db.models import User
        actual_user = db.query(User).filter((User.id == student_user_id) | (User.username == student_user_id)).first()
        target_uid = actual_user.id if actual_user else student_user_id

        student_entry = (
            db.query(CredentialVault)
            .filter(
                CredentialVault.user_id == target_uid,
                CredentialVault.category == category,
                CredentialVault.is_admin_key == False,
            )
            .first()
        )
        if student_entry and student_entry.encrypted_api_key:
            try:
                decrypted = decrypt_api_key(student_entry.encrypted_api_key)
                return {
                    "category": category,
                    "provider": student_entry.provider,
                    "model_name": student_entry.model_name,
                    "base_url": student_entry.base_url,
                    "voice": student_entry.voice,
                    "api_key": decrypted,
                    "key_preview": student_entry.key_preview,
                    "source": "student_byok",
                    "is_free": True,
                    "label": "Your BYOK Key (Free)",
                }
            except Exception:
                pass

    # Tier 3: Environment Fallback (.env)
    return get_default_env_config(category)


def get_student_model_matrix(db: Session, student_user_id: str) -> dict[str, dict[str, Any]]:
    """
    Returns the read-only AI engines status matrix for the student dashboard.
    Enforces strict institution-managed model governance:
    - Zero candidate key capture
    - Admin-configured credentials are active
    - Admin secret API keys are never exposed (masked as 'Institution Enforced (Protected)')
    """
    from src.api.db.models import User
    actual_user = db.query(User).filter((User.id == student_user_id) | (User.username == student_user_id)).first()
    target_uid = actual_user.id if actual_user else student_user_id

    matrix = {}
    for cat in VALID_CATEGORIES:
        admin_entry = (
            db.query(CredentialVault)
            .filter(
                CredentialVault.is_admin_key == True,
                CredentialVault.category == cat,
            )
            .first()
        )
        admin_locked = admin_entry is not None and bool(admin_entry.encrypted_api_key)
        active = resolve_model_config(db, cat, student_user_id=target_uid)

        active_preview = "Institution Enforced (Protected)" if admin_locked else active.get("key_preview")

        matrix[cat] = {
            "has_byok": False,
            "admin_locked": True,
            "saved_provider": None,
            "saved_model": None,
            "saved_preview": None,
            "saved_base_url": None,
            "saved_voice": None,
            "active_source": active.get("source"),
            "active_label": "Institution Default Key (Admin Controlled)",
            "active_provider": active.get("provider"),
            "active_model": active.get("model_name"),
            "active_preview": active_preview,
            "is_free": False,
            "voice": active.get("voice"),
        }
    return matrix


def get_admin_model_matrix(db: Session) -> dict[str, dict[str, Any]]:
    """
    Returns the complete 3-model configuration matrix for the admin dashboard:
    thinking, stt, and tts. Shows active admin-provided keys and fallback states.
    Visible only to Admin.
    """
    matrix = {}
    for cat in VALID_CATEGORIES:
        saved = (
            db.query(CredentialVault)
            .filter(
                CredentialVault.is_admin_key == True,
                CredentialVault.category == cat,
            )
            .first()
        )
        active = resolve_model_config(db, cat, student_user_id=None)
        matrix[cat] = {
            "is_configured": saved is not None,
            "provider": saved.provider if saved else active.get("provider"),
            "model_name": saved.model_name if saved else active.get("model_name"),
            "key_preview": saved.key_preview if saved else active.get("key_preview"),
            "base_url": saved.base_url if saved else active.get("base_url"),
            "voice": saved.voice if saved else active.get("voice"),
            "source": "admin_provided" if saved else active.get("source"),
            "label": "Admin Configured" if saved else active.get("label"),
        }
    return matrix
