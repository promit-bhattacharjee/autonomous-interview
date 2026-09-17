import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.api.db.models import Base, CredentialVault, ModelCategory, User, UserRole
from src.api.security.auth import create_access_token, hash_password
from src.api.security.vault import decrypt_api_key, encrypt_api_key, mask_api_key
from src.api.services import vault_service
from interview.helper import get_speech_llm, get_thinking_llm, resolve_candidate_thinking_llm


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_encryption_and_masking():
    raw_key = "sk-live-1234567890abcdef"
    encrypted = encrypt_api_key(raw_key)
    assert encrypted != raw_key
    assert decrypt_api_key(encrypted) == raw_key

    preview = mask_api_key(raw_key)
    assert preview.startswith("sk-")
    assert preview.endswith("cdef")


def test_vault_service_admin_custody_and_candidate_rejection(test_db):
    user = User(
        username="test_student",
        email="student@example.com",
        hashed_password=hash_password("pass"),
        role=UserRole.STUDENT,
    )
    test_db.add(user)
    test_db.commit()

    # Candidate attempting to save key MUST be rejected with 403 Forbidden
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        vault_service.save_model_credential(
            db=test_db,
            category="thinking",
            provider="openrouter",
            api_key="sk-or-v1-my-thinking-key-123",
            model_name="deepseek/deepseek-chat",
            user_id=user.id,
            is_admin=False,
        )
    assert exc_info.value.status_code == 403
    assert "Candidate API key capture is disabled" in exc_info.value.detail

    # Candidate attempting to delete key MUST be rejected with 403 Forbidden
    with pytest.raises(HTTPException) as exc_info_del:
        vault_service.delete_model_credential(
            db=test_db,
            category="thinking",
            user_id=user.id,
            is_admin=False,
        )
    assert exc_info_del.value.status_code == 403

    # Admin saving key succeeds
    admin_entry = vault_service.save_model_credential(
        db=test_db,
        category="thinking",
        provider="openrouter",
        api_key="sk-or-v1-admin-thinking-key-123",
        model_name="deepseek/deepseek-chat",
        user_id=None,
        is_admin=True,
    )
    assert admin_entry.category == "thinking"
    assert admin_entry.provider == "openrouter"
    assert admin_entry.model_name == "deepseek/deepseek-chat"
    assert admin_entry.is_admin_key is True
    assert decrypt_api_key(admin_entry.encrypted_api_key) == "sk-or-v1-admin-thinking-key-123"

    # Admin deleting key succeeds
    deleted = vault_service.delete_model_credential(
        db=test_db,
        category="thinking",
        user_id=None,
        is_admin=True,
    )
    assert deleted is True


def test_hierarchical_resolution_and_admin_governance(test_db):
    student = User(
        username="alice",
        email="alice@example.com",
        hashed_password=hash_password("pass"),
        role=UserRole.STUDENT,
    )
    test_db.add(student)
    test_db.commit()

    # Tier 3 (.env fallback) when no keys stored
    res_env = vault_service.resolve_model_config(test_db, "thinking", student_user_id=student.id)
    assert res_env["source"] == "env_fallback"
    assert res_env["is_free"] is True

    # Admin configures an institution key
    vault_service.save_model_credential(
        db=test_db,
        category="thinking",
        provider="openrouter",
        api_key="sk-or-admin-institution-key",
        model_name="deepseek/deepseek-chat",
        user_id=None,
        is_admin=True,
    )

    # Student session resolves the Admin institution key directly
    res_admin = vault_service.resolve_model_config(test_db, "thinking", student_user_id=student.id)
    assert res_admin["source"] == "admin_provided"
    assert res_admin["api_key"] == "sk-or-admin-institution-key"
    assert res_admin["model_name"] == "deepseek/deepseek-chat"
    assert res_admin["is_free"] is False

    # Candidate cannot mutate or override
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        vault_service.save_model_credential(
            db=test_db,
            category="thinking",
            provider="deepseek",
            api_key="sk-student-byok-key",
            user_id=student.id,
            is_admin=False,
        )
    assert exc_info.value.status_code == 403


def test_stt_and_tts_resolution(test_db):
    student = User(
        username="bob",
        email="bob@example.com",
        hashed_password=hash_password("pass"),
        role=UserRole.STUDENT,
    )
    test_db.add(student)
    test_db.commit()

    # Configure STT as Admin
    vault_service.save_model_credential(
        db=test_db,
        category="stt",
        provider="groq",
        api_key="gsk-whisper-admin-key",
        model_name="whisper-large-v3-turbo",
        user_id=None,
        is_admin=True,
    )
    stt_cfg = vault_service.resolve_model_config(test_db, "stt", student_user_id=student.id)
    assert stt_cfg["source"] == "admin_provided"
    assert stt_cfg["api_key"] == "gsk-whisper-admin-key"
    assert stt_cfg["model_name"] == "whisper-large-v3-turbo"

    # Configure TTS as Admin
    vault_service.save_model_credential(
        db=test_db,
        category="tts",
        provider="deepgram",
        api_key="dg-aura-admin-key",
        model_name="aura-asteria-en",
        voice="Asteria",
        user_id=None,
        is_admin=True,
    )
    tts_cfg = vault_service.resolve_model_config(test_db, "tts", student_user_id=student.id)
    assert tts_cfg["source"] == "admin_provided"
    assert tts_cfg["voice"] == "Asteria"
    assert tts_cfg["api_key"] == "dg-aura-admin-key"
    assert tts_cfg["model_name"] == "aura-asteria-en"


def test_student_and_admin_matrices(test_db):
    student = User(
        username="charlie",
        email="charlie@example.com",
        hashed_password=hash_password("pass"),
        role=UserRole.STUDENT,
    )
    test_db.add(student)
    test_db.commit()

    matrix = vault_service.get_student_model_matrix(test_db, student.id)
    assert "thinking" in matrix
    assert "stt" in matrix
    assert "tts" in matrix
    assert matrix["thinking"]["has_byok"] is False

    admin_matrix = vault_service.get_admin_model_matrix(test_db)
    assert "thinking" in admin_matrix
    assert "stt" in admin_matrix
    assert "tts" in admin_matrix


def test_helper_dynamic_llm_parameters():
    # Test get_thinking_llm with explicit dynamic arguments
    llm = get_thinking_llm(
        model_name="gpt-4o-mini",
        api_key="sk-test-custom-key-12345",
        base_url="https://api.openai.com/v1",
        provider="openai",
    )
    assert llm.model_name == "gpt-4o-mini"

    # Test get_speech_llm with dynamic arguments
    speech_llm = get_speech_llm(
        model_name="gpt-4o-mini",
        api_key="sk-test-custom-key-12345",
        provider="openai",
    )
    assert speech_llm is not None
