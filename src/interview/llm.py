from typing import Any, Optional, Sequence
from dotenv import find_dotenv, load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

# Automatically load environment variables from .env file
load_dotenv(find_dotenv(usecwd=True))


def get_llm(
    model_name: str = "gemini-3.6-flash",
    model_provider: str = "google_genai",
    temperature: float = 0.0,
    tools: Optional[Sequence[Any]] = None,
    **kwargs: Any,
) -> BaseChatModel:
    """
    Initialize any Chat Model across providers
    (Google, OpenAI, Anthropic, Groq, Ollama, etc.) with optional tool binding.
    """
    model = init_chat_model(
        model=model_name,
        model_provider=model_provider,
        temperature=temperature,
        **kwargs,
    )
    if tools:
        return model.bind_tools(tools)
    return model
