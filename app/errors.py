"""Error codes and safe mapping of OpenAI SDK errors.

Only the exception type, status code and error code are used. The exception
message text is never read, so keys and request details cannot leak.
"""

import logging
import time

import openai

logger = logging.getLogger("pawleen.errors")

ERROR_CODES = frozenset(
    {
        "visitor_limit", "global_cap", "config_error", "no_animal", "bad_costume",
        "gatekeeper_failed", "credits_depleted", "temporary_failure", "refused",
        "maker_failed", "maker_timeout", "pipeline_timeout", "judge_locked",
        "bad_upload", "wonky", "not_verified",
    }
)  # fmt: skip


class PawleenError(Exception):
    """An error with a defined code that maps to a spooky message."""

    def __init__(self, code):
        if code not in ERROR_CODES:
            raise ValueError("unknown error code")
        super().__init__(code)
        self.code = code


def _error_code(exc):
    """Return the OpenAI `error.code` string, or None."""
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) else None


def classify_openai_error(exc):
    """Map any exception to one defined error code and log as needed."""
    if isinstance(exc, PawleenError):
        return exc.code

    # 401, 403 and 404 (for example a retired model) are setup problems.
    # A retry cannot fix them. Log the category and exception type only.
    if isinstance(
        exc,
        (openai.AuthenticationError, openai.PermissionDeniedError, openai.NotFoundError),
    ):
        logger.error("category=config_error type=%s", type(exc).__name__)
        return "config_error"

    if isinstance(exc, openai.RateLimitError):
        if _error_code(exc) == "insufficient_quota":
            # Exactly one line: time and category only.
            logger.error("%s category=credits_depleted", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
            return "credits_depleted"
        return "temporary_failure"

    if isinstance(exc, openai.BadRequestError):
        if _error_code(exc) == "moderation_blocked":
            return "refused"
        return "temporary_failure"

    if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError)):
        return "temporary_failure"

    if isinstance(exc, openai.APIStatusError):
        return "temporary_failure"

    # Unknown: log the type only, never str(exc).
    logger.error("unexpected error type=%s", type(exc).__name__)
    return "temporary_failure"
