import os
from typing import Any, Optional, Sequence
from dotenv import find_dotenv, load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

# Automatically load environment variables from nearest .env file
load_dotenv(find_dotenv(usecwd=True))


def get_thinking_llm(
    model_name: Optional[str] = None,
    temperature: float = 0.0,
    **kwargs: Any,
) -> BaseChatModel:
    """
    Initializes the OpenRouter thinking model (DeepSeek V3 by default).
    Used for reasoning, question generation, answer evaluation, and final evaluation.
    Fast, highly capable, and token-cost-efficient.
    """
    model = model_name or os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")
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
        max_retries=3,
        **kwargs,
    )


def get_speech_llm(
    model_name: str = "gemini-3.6-flash",
    temperature: float = 0.3,
    **kwargs: Any,
) -> BaseChatModel:
    """
    Initializes Google Gemini model for conversational speech formulation.
    STT and TTS are handled separately via GeminiSTT and GeminiTTS plugins.
    """
    return init_chat_model(
        model=model_name,
        model_provider="google_genai",
        temperature=temperature,
        **kwargs,
    )


def get_llm(
    model_name: Optional[str] = None,
    model_provider: Optional[str] = None,
    temperature: float = 0.0,
    tools: Optional[Sequence[Any]] = None,
    **kwargs: Any,
) -> BaseChatModel:
    """
    Universal LLM selector.
    Defaults to OpenRouter thinking model unless Google GenAI is explicitly specified.
    """
    if model_provider == "google_genai":
        model = get_speech_llm(model_name=model_name or "gemini-2.5-flash", temperature=temperature, **kwargs)
    else:
        model = get_thinking_llm(model_name=model_name, temperature=temperature, **kwargs)

    if tools:
        return model.bind_tools(tools)
    return model
