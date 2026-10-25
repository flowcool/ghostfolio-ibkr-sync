"""Run-local failures and delivery bookkeeping; external summaries use fixed codes."""

from typing import Any, NotRequired, TypedDict

import requests


class Failure(TypedDict):
    stage: str
    reason: str
    ordinal: int | None


class RunOutcome(TypedDict):
    failures: list[Failure]
    dropped: int
    accounts_total: int
    accounts_failed: int
    token_expiry_days: NotRequired[int]
    forced_preview: NotRequired[str]
    corporate_notification: NotRequired[dict[str, Any]]
    corporate_maintenance: NotRequired[bool]


# Allowed failure reasons per stage. External summaries use only these codes,
# counts and 1-based ordinals. The corporate_notification field is private
# delivery bookkeeping; its paths and fingerprints must never enter a summary.
OUTCOME_REASONS = {
    "config": ("invalid_configuration",),
    "mapping": ("invalid_mapping",),
    "review": ("review_unavailable",),
    "corporate_actions": ("trade_hold",),
    "ghost_auth": ("login_failed",),
    "ghost_startup": ("activities_unavailable", "token_rejected", "invalid_identity"),
    "account": ("account_failed", "unexpected_error"),
    "unexpected": ("unhandled_error",),
}
MAX_OUTCOME_FAILURES = 20


def is_token_rejection(exc: BaseException) -> bool:
    """True when Ghostfolio answered 401/403, i.e. the bearer token is expired or invalid."""
    response = getattr(exc, "response", None)
    return (isinstance(exc, requests.HTTPError) and response is not None
            and response.status_code in (401, 403))


def new_run_outcome() -> RunOutcome:
    """Return an empty run-local outcome."""
    return {"failures": [], "dropped": 0, "accounts_total": 0, "accounts_failed": 0}


def record_failure(outcome: RunOutcome, stage: str, reason: str, ordinal: object = None) -> None:
    """Record one failure; unknown codes collapse to unexpected/unhandled_error."""
    if reason not in OUTCOME_REASONS.get(stage, ()):
        stage, reason = "unexpected", "unhandled_error"
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1:
        ordinal = None
    if len(outcome["failures"]) >= MAX_OUTCOME_FAILURES:
        outcome["dropped"] += 1
        return
    outcome["failures"].append({"stage": stage, "reason": reason, "ordinal": ordinal})
