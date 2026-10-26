"""Compatibility module: aliases GeminiClient and get_gemini to GroqClient."""

from app.services.ai.groq_client import (
    AiAuthFailedError,
    AiBadResponseError,
    AiBaseError,
    AiNotConfiguredError,
    AiQuotaExceededError,
    AiTimeoutError,
    GroqClient,
    get_groq,
    redact_secrets,
)

# Aliases for backward compatibility
GeminiClient = GroqClient
get_gemini = get_groq

__all__ = [
    "AiAuthFailedError",
    "AiBadResponseError",
    "AiBaseError",
    "AiNotConfiguredError",
    "AiQuotaExceededError",
    "AiTimeoutError",
    "GeminiClient",
    "GroqClient",
    "get_gemini",
    "get_groq",
    "redact_secrets",
]
