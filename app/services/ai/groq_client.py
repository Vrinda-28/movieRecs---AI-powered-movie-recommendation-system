"""Groq API client wrapper using the official groq SDK.

Provides structured JSON generation adhering to Pydantic schemas.
"""

import asyncio
import json
import logging
import re
from typing import Optional, Type, TypeVar

import groq
from pydantic import BaseModel, ValidationError

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class AiBaseError(Exception):
    """Base exception for all AI-related errors."""

    def __init__(self, detail: str, status_code: int = 500):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class AiNotConfiguredError(AiBaseError):
    """Raised when AI features are invoked but GROQ_API_KEY is not set."""

    def __init__(self, detail: str = "ai_not_configured"):
        super().__init__(detail=detail, status_code=503)


class AiAuthFailedError(AiBaseError):
    """Raised when Groq authentication or permission fails."""

    def __init__(self, detail: str = "ai_auth_failed"):
        super().__init__(detail=detail, status_code=502)


class AiQuotaExceededError(AiBaseError):
    """Raised when Groq rate limit or quota is exhausted."""

    def __init__(self, detail: str = "ai_quota_exceeded"):
        super().__init__(detail=detail, status_code=429)


class AiTimeoutError(AiBaseError):
    """Raised when a call to Groq times out or network connection fails."""

    def __init__(self, detail: str = "ai_timeout"):
        super().__init__(detail=detail, status_code=504)


class AiBadResponseError(AiBaseError):
    """Raised when Groq returns malformed, blocked, or unparseable output."""

    def __init__(self, detail: str = "ai_bad_response"):
        super().__init__(detail=detail, status_code=502)


def redact_secrets(text: str, key: Optional[str] = None) -> str:
    """Removes API keys or secret tokens from error messages."""
    if not text:
        return text
    clean = re.sub(r"gsk_[0-9A-Za-z_-]{20,}", "[REDACTED_KEY]", str(text))
    clean = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[REDACTED_KEY]", clean)
    if key and len(key) > 4:
        clean = clean.replace(key, "[REDACTED_KEY]")
    return clean


class GroqClient:
    """Wrapper around groq.AsyncGroq Client exposing structured JSON generation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self._api_key = api_key if api_key is not None else settings.GROQ_API_KEY
        self.model = model or settings.GROQ_MODEL
        self.timeout = timeout if timeout is not None else settings.GROQ_TIMEOUT_SECONDS
        self._client: Optional[groq.AsyncGroq] = None

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key and self._api_key.strip())

    def _get_client(self) -> groq.AsyncGroq:
        if not self.is_configured:
            raise AiNotConfiguredError()
        if self._client is None:
            self._client = groq.AsyncGroq(
                api_key=self._api_key,
                timeout=self.timeout,
            )
        return self._client

    async def generate_json(self, system: str, user: str, schema: Type[T]) -> T:
        """Generates structured JSON adhering to the given Pydantic schema.

        Retries once on transient errors (network/server/parse errors).
        Does NOT retry on auth (401/403) or quota (429) errors.
        """
        client = self._get_client()

        schema_json = schema.model_json_schema()
        system_instruction = (
            f"{system}\n\n"
            f"You MUST output valid JSON strictly matching this JSON schema:\n"
            f"{json.dumps(schema_json, indent=2)}\n"
            f"Do not include markdown code block syntax (like ```json). Return ONLY the raw JSON object."
        )

        last_error: Optional[Exception] = None

        for attempt in range(2):
            try:
                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": user},
                        ],
                        response_format={"type": "json_object"},
                    ),
                    timeout=self.timeout,
                )

                raw_text = response.choices[0].message.content or ""
                clean_text = raw_text.strip()
                if clean_text.startswith("```"):
                    clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
                    clean_text = re.sub(r"\s*```$", "", clean_text).strip()

                if not clean_text:
                    raise AiBadResponseError("Empty response from AI model")

                return schema.model_validate_json(clean_text)

            except (AiNotConfiguredError, AiAuthFailedError, AiQuotaExceededError):
                raise

            except (asyncio.TimeoutError, groq.APITimeoutError) as exc:
                last_error = exc
                logger.warning(
                    f"Groq call timed out after {self.timeout}s (attempt {attempt + 1})"
                )
                if attempt == 1:
                    raise AiTimeoutError() from exc

            except (groq.AuthenticationError, groq.PermissionDeniedError) as exc:
                redacted_msg = redact_secrets(str(exc), self._api_key)
                logger.error(f"Groq auth error: {redacted_msg}")
                raise AiAuthFailedError() from exc

            except groq.RateLimitError as exc:
                redacted_msg = redact_secrets(str(exc), self._api_key)
                logger.warning(f"Groq quota/rate limit exceeded: {redacted_msg}")
                raise AiQuotaExceededError() from exc

            except groq.NotFoundError as exc:
                redacted_msg = redact_secrets(str(exc), self._api_key)
                logger.error(f"Groq model not found ({self.model}): {redacted_msg}")
                raise AiBadResponseError("Model unavailable or not found") from exc

            except (groq.APIConnectionError, groq.InternalServerError) as exc:
                last_error = exc
                redacted_msg = redact_secrets(str(exc), self._api_key)
                logger.warning(
                    f"Groq API connection/server error (attempt {attempt + 1}): {redacted_msg}"
                )
                if attempt == 1:
                    raise AiBadResponseError() from exc

            except (groq.APIError, groq.GroqError) as exc:
                last_error = exc
                redacted_msg = redact_secrets(str(exc), self._api_key)
                logger.warning(
                    f"Groq API error (attempt {attempt + 1}): {redacted_msg}"
                )
                if attempt == 1:
                    raise AiBadResponseError() from exc

            except (ValidationError, ValueError) as exc:
                last_error = exc
                redacted_msg = redact_secrets(str(exc), self._api_key)
                logger.warning(
                    f"Groq output failed schema validation (attempt {attempt + 1}): {redacted_msg}"
                )
                if attempt == 1:
                    raise AiBadResponseError("Malformed structured output") from exc

            except Exception as exc:
                last_error = exc
                redacted_msg = redact_secrets(str(exc), self._api_key)
                logger.warning(
                    f"Groq unexpected exception (attempt {attempt + 1}): {redacted_msg}"
                )
                if attempt == 1:
                    raise AiBadResponseError() from exc

        if isinstance(
            last_error,
            (
                AiTimeoutError,
                AiBadResponseError,
                AiQuotaExceededError,
                AiAuthFailedError,
            ),
        ):
            raise last_error
        raise AiBadResponseError()


_default_groq_client: Optional[GroqClient] = None


def get_groq() -> GroqClient:
    """FastAPI dependency provider for GroqClient."""
    global _default_groq_client
    if _default_groq_client is None:
        _default_groq_client = GroqClient()
    return _default_groq_client


# Backward-compatibility aliases
GeminiClient = GroqClient
get_gemini = get_groq
get_ai_client = get_groq
