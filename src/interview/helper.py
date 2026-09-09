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

def get_thinking_llm(
    model_name: Optional[str] = None,
    temperature: float = 0.0,
    **kwargs: Any,
) -> BaseChatModel:
    """
    Initializes the OpenRouter thinking model (DeepSeek V4 Flash 0731 by default).
    Configured directly from environment variables.
    """
    model = model_name or os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash-0731")
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    if api_key and "OPENAI_API_KEY" not in os.environ:
        os.environ["OPENAI_API_KEY"] = api_key
    if base_url and "OPENAI_BASE_URL" not in os.environ:
        os.environ["OPENAI_BASE_URL"] = base_url

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        max_retries=2,
        timeout=60,
        **kwargs,
    )


def get_speech_llm(
    model_name: str = "gemini-3.6-flash",
    temperature: float = 0.3,
    **kwargs: Any,
) -> BaseChatModel:
    """
    Initializes Google Gemini model for conversational speech formulation.
    """
    return init_chat_model(
        model=model_name,
        model_provider="google_genai",
        temperature=temperature,
        **kwargs,
    )


def get_structured_thinking_llm(schema: Any, temperature: float = 0.0):
    """
    Returns a structured thinking model with automatic fallback to LLaMA-3.3-70B.
    Statically configured from environment variables.
    """
    primary = get_thinking_llm(temperature=temperature)
    fallback = get_thinking_llm(model_name="meta-llama/llama-3.3-70b-instruct", temperature=temperature)
    try:
        return primary.with_structured_output(schema).with_fallbacks([fallback.with_structured_output(schema)])
    except Exception:
        return primary.with_structured_output(schema)



