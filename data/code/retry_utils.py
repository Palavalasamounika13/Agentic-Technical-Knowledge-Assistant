"""Retry helpers used by the payment gateway client."""
import random
import time

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class RetryError(Exception):
    """Raised when all retry attempts are used up."""


def backoff_delay(attempt: int, base: float = 1.0, cap: float = 30.0) -> float:
    """Exponential backoff with jitter: base * 2^attempt, capped, plus up to 10% random jitter."""
    delay = min(cap, base * (2 ** attempt))
    return delay + random.uniform(0, delay * 0.1)


def call_with_retry(fn, max_retries: int = 3):
    """Call fn(). Retry when it raises an error whose status_code is retryable."""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as err:
            status = getattr(err, "status_code", None)
            if status not in RETRYABLE_STATUS:
                raise  # non-retryable errors fail immediately
            last_error = err
            if attempt < max_retries:
                time.sleep(backoff_delay(attempt))
    raise RetryError(f"gave up after {max_retries} retries") from last_error
