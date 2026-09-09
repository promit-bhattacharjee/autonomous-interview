"""
Backward compatibility layer: re-exports LLM initializers and helpers from interview.helper.
New code should import directly from interview.helper.
"""
from interview.helper import (
    ensure_text_content,
    get_speech_llm,
    get_structured_thinking_llm,
    get_thinking_llm,
)

__all__ = [
    "get_thinking_llm",
    "get_speech_llm",
    "get_structured_thinking_llm",
    "ensure_text_content",
]
