"""Minimal resilient HTTP helpers for AI provider calls."""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class AIHTTPError(RuntimeError):
    """Raised when an AI provider request fails."""


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    timeout_seconds: float = 30.0
    backoff_base_seconds: float = 0.75
    jitter_seconds: float = 0.25


def post_json(
    *,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    retry: RetryPolicy | None = None,
) -> dict[str, Any]:
    """POST JSON and return decoded JSON body with bounded retries."""
    policy = retry or RetryPolicy()
    encoded = json.dumps(payload).encode("utf-8")
    last_error: Exception | None = None

    for attempt in range(1, policy.attempts + 1):
        req = urllib.request.Request(
            url=url,
            method="POST",
            data=encoded,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                **headers,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=policy.timeout_seconds) as resp:  # noqa: S310
                raw = resp.read().decode("utf-8", errors="replace")
                decoded: object = json.loads(raw)
                if not isinstance(decoded, dict):
                    raise AIHTTPError(
                        f"Non-object JSON response from {url}: {type(decoded).__name__}"
                    )
                return decoded
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except OSError:
                body = ""
            last_error = AIHTTPError(
                f"{url} HTTP {exc.code}: {body[:600]}".strip()
            )
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            last_error = exc

        if attempt < policy.attempts:
            sleep_for = policy.backoff_base_seconds * (2 ** (attempt - 1))
            if policy.jitter_seconds > 0:
                sleep_for += random.uniform(0, policy.jitter_seconds)  # noqa: S311
            time.sleep(sleep_for)

    raise AIHTTPError(f"Request failed for {url}: {last_error}") from last_error


__all__ = ["AIHTTPError", "RetryPolicy", "post_json"]
