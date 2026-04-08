import random
from typing import Any, Callable, Optional, Protocol, TypeVar, cast

from .definitions import RETRYABLE_EXCEPTIONS, RETRYABLE_STATUS_CODES

try:
    from tenacity import retry as imported_retry
    from tenacity import retry_if_exception as imported_retry_if_exception
    from tenacity import stop_after_attempt as imported_stop_after_attempt

    tenacity_retry: Any = imported_retry
    tenacity_retry_if_exception: Any = imported_retry_if_exception
    tenacity_stop_after_attempt: Any = imported_stop_after_attempt

    TENACITY_AVAILABLE = True
except ImportError:
    tenacity_retry = cast(Any, None)
    tenacity_retry_if_exception = cast(Any, None)
    tenacity_stop_after_attempt = cast(Any, None)
    TENACITY_AVAILABLE = False

WrappedCallable = TypeVar("WrappedCallable", bound=Callable[..., Any])


class RetryOutcomeLike(Protocol):
    """Outcome protocol compatible with tenacity retry state."""

    def exception(self) -> Optional[BaseException]:
        """Return the exception for the current attempt, if any."""


class RetryStateLike(Protocol):
    """Minimal retry state interface used by retry handlers."""

    attempt_number: int
    outcome: RetryOutcomeLike


class ManualRetryOutcome:
    """Simple outcome object for the manual retry fallback path."""

    def __init__(self, exception: BaseException) -> None:
        self._exception = exception

    def exception(self) -> BaseException:
        return self._exception


class ManualRetryState:
    """Fallback retry state matching the subset of tenacity we use."""

    def __init__(self, exception: BaseException, attempt_number: int) -> None:
        self.attempt_number = attempt_number
        self.outcome: RetryOutcomeLike = ManualRetryOutcome(exception)


def calculate_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    """Calculate exponential backoff with jitter."""
    attempt = max(1, attempt)
    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
    jitter = random.uniform(0, delay * 0.1)
    return delay + jitter


def is_retryable_error(exception: Optional[BaseException]) -> bool:
    """Classify if an error is retryable."""
    if exception is None:
        return False

    if isinstance(exception, RETRYABLE_EXCEPTIONS):
        return True

    try:
        error_str = str(exception).lower()
        for code in RETRYABLE_STATUS_CODES:
            if str(code) in error_str:
                return True
    except Exception:
        return False

    return False


def is_rate_limit_error(exception: Optional[BaseException]) -> bool:
    """Specifically detect HTTP 429 (rate limiting) errors."""
    if exception is None:
        return False

    try:
        error_str = str(exception).lower()
        if "429" in error_str or "too many requests" in error_str or "rate limit" in error_str:
            return True
    except Exception:
        return False

    return False


def build_retry_decorator(
    should_retry: Callable[[BaseException], bool],
    max_retries: int,
    before_sleep: Optional[Callable] = None,
) -> Callable[[WrappedCallable], WrappedCallable]:
    """Build the tenacity retry decorator when the dependency is available."""
    if (
        not TENACITY_AVAILABLE
        or tenacity_retry is None
        or tenacity_retry_if_exception is None
        or tenacity_stop_after_attempt is None
    ):
        raise RuntimeError("tenacity is not installed")
    return tenacity_retry(
        stop=tenacity_stop_after_attempt(max_retries),
        retry=tenacity_retry_if_exception(should_retry),
        before_sleep=before_sleep,
        reraise=True,
    )