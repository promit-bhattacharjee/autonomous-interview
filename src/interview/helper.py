import os
from typing import Any, Optional
from dotenv import find_dotenv, load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

# Automatically load environment variables from nearest .env file
load_dotenv(find_dotenv(usecwd=True))


# ==============================================================================
# 1. MESSAGE & CONTEXT NORMALIZATION HELPERS
# ==============================================================================

def ensure_text_content(msg: AIMessage) -> AIMessage:
    """Normalizes multimodal content blocks into clean string text."""
    if isinstance(msg.content, list):
        text_parts = [
            p.get("text", "") if isinstance(p, dict) else str(p)
            for p in msg.content
        ]
        msg.content = "".join(text_parts).strip()
    return msg


# ==============================================================================
# 2. STATIC MODEL INITIALIZATION (.env Driven)
# ==============================================================================
# 2. DYNAMIC & STATIC MODEL INITIALIZATION (.env & Vault Driven)
# ==============================================================================

def get_thinking_llm(
    model_name: Optional[str] = None,
    temperature: float = 0.0,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    provider: Optional[str] = None,
    **kwargs: Any,
) -> BaseChatModel:
    """
    Initializes the thinking LLM brain dynamically.
    Supports OpenRouter, Google Gemini, OpenAI, and DeepSeek.
    Falls back cleanly to environment variables if parameters not supplied.
    """
    prov = (provider or "openrouter").lower()
    resolved_api_key = (api_key or os.getenv("OPENROUTER_API_KEY") or "").strip() or "mock-openrouter-key-for-test"
    resolved_base_url = base_url or os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    resolved_model = model_name or os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash-0731")

    if prov in ("google", "gemini", "google_genai"):
        google_key = (api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip() or "mock-google-key-for-test"
        return init_chat_model(
            model=resolved_model if model_name else "gemini-3.6-flash",
            model_provider="google_genai",
            api_key=google_key,
            temperature=temperature,
            **kwargs,
        )

    if resolved_api_key and "OPENAI_API_KEY" not in os.environ:
        os.environ["OPENAI_API_KEY"] = resolved_api_key
    if resolved_base_url and "OPENAI_BASE_URL" not in os.environ:
        os.environ["OPENAI_BASE_URL"] = resolved_base_url

    return ChatOpenAI(
        model=resolved_model,
        api_key=resolved_api_key,
        base_url=resolved_base_url,
        temperature=temperature,
        max_retries=2,
        timeout=60,
        **kwargs,
    )


def get_speech_llm(
    model_name: str = "gemini-3.6-flash",
    temperature: float = 0.3,
    api_key: Optional[str] = None,
    provider: Optional[str] = None,
    **kwargs: Any,
) -> BaseChatModel:
    """
    Initializes model for conversational speech formulation.
    Supports dynamic API keys and provider selection.
    """
    prov = (provider or "google").lower()
    if prov in ("openai", "openrouter"):
        resolved_key = (api_key or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip() or "mock-key-for-test"
        return ChatOpenAI(
            model=model_name if model_name != "gemini-3.6-flash" else "gpt-4o-mini",
            api_key=resolved_key,
            temperature=temperature,
            **kwargs,
        )

    resolved_key = (api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip() or "mock-google-key-for-test"
    return init_chat_model(
        model=model_name,
        model_provider="google_genai",
        api_key=resolved_key,
        temperature=temperature,
        **kwargs,
    )


def get_structured_thinking_llm(
    schema: Any,
    temperature: float = 0.0,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model_name: Optional[str] = None,
    provider: Optional[str] = None,
):
    """
    Returns a structured thinking model with automatic fallback.
    Accepts dynamic credentials and model parameters.
    """
    primary = get_thinking_llm(
        model_name=model_name,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
        provider=provider,
    )
    fallback = get_thinking_llm(
        model_name="meta-llama/llama-3.3-70b-instruct",
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
        provider=provider,
    )
    try:
        return primary.with_structured_output(schema).with_fallbacks([fallback.with_structured_output(schema)])
    except Exception:
        return primary.with_structured_output(schema)


def resolve_candidate_thinking_llm(
    user_id: Optional[str] = None,
    temperature: float = 0.0,
    **kwargs: Any,
) -> BaseChatModel:
    """
    Resolves the Thinking LLM using the 3-tier hierarchy:
    Tier 1 (Student BYOK) -> Tier 2 (Admin Default) -> Tier 3 (.env Fallback).
    """
    if user_id:
        try:
            try:
                from src.api.db.session import SessionLocal
                from src.api.services.vault_service import resolve_model_config
            except (ImportError, ModuleNotFoundError):
                import sys
                from pathlib import Path
                web_api_path = str(Path(__file__).resolve().parent.parent.parent / "services" / "web_api")
                if web_api_path not in sys.path:
                    sys.path.insert(0, web_api_path)
                from src.api.db.session import SessionLocal
                from src.api.services.vault_service import resolve_model_config

            db = SessionLocal()
            try:
                cfg = resolve_model_config(db, "thinking", student_user_id=user_id)
                if cfg and cfg.get("api_key"):
                    return get_thinking_llm(
                        model_name=cfg.get("model_name"),
                        temperature=temperature,
                        api_key=cfg.get("api_key"),
                        base_url=cfg.get("base_url"),
                        provider=cfg.get("provider"),
                        **kwargs,
                    )
            finally:
                db.close()
        except Exception:
            pass

    return get_thinking_llm(temperature=temperature, **kwargs)



