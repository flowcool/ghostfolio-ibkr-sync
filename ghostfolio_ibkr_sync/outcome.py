"""Run-local failures and delivery bookkeeping; external summaries use fixed codes."""

import logging
from typing import Any, NotRequired, TypedDict

import requests


class Failure(TypedDict):
    stage: str
    reason: str
    ordinal: int | None


class RunOutcome(TypedDict):
    actions: dict[str, set[str]]
    failures: list[Failure]
    dropped: int
    accounts_total: int
    accounts_failed: int
    token_expiry_days: NotRequired[int]
    forced_preview: NotRequired[str]
    corporate_notification: NotRequired[dict[str, Any]]
    corporate_maintenance: NotRequired[bool]
    delivery: NotRequired[str]


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
    return {"actions": {}, "failures": [], "dropped": 0, "accounts_total": 0, "accounts_failed": 0}


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


# Private event keys never enter external summaries. Instructions and resolution
# proof are fixed text; callers supply only the observed code and private scope.
ACTION_INSTRUCTIONS = {
    "review_approval": "Read the exact proposal in ACTIVITY_REVIEW_FILE. Edit only approve between runs; lowercase literal yes approves an eligible normal-run correction. Resolution: current evidence confirms the intended correction or documented manual resolution.",
    "review_evidence": "Inspect ACTIVITY_REVIEW_FILE and obtain the stated missing proof. yes cannot make blocked work executable. Resolution: current source and destination evidence qualify the proposal.",
    "review_maintenance": "Follow the historical maintenance preparation guide and obtain separate operation authorization. Normal sync cannot execute it. Resolution: verified maintenance or documented manual resolution.",
    "review_uncertain": "Inspect preserved journal and destination readback. Do not resend, delete or edit the journal. Resolution: exact readback confirms the request outcome.",
    "mapping_unverified": "Verify the security in Ghostfolio or correct MAPPING_FILE. Resolution: an explicit mapping matches the intended destination security.",
    "dividend_check": "Inspect the private dividend comparison and source evidence in Ghostfolio. Do not invent or resend a transaction. Resolution: current source and destination evidence agree or the stated discrepancy is resolved.",
}


def record_action(outcome: RunOutcome | None, reason: str, key: str) -> None:
    """Register an explicit decision once per private event and reason."""
    if reason not in ACTION_INSTRUCTIONS:
        raise ValueError("Unknown required-action reason")
    if outcome is None:
        return
    keys = outcome["actions"].setdefault(reason, set())
    if key not in keys:
        keys.add(key)
        logging.getLogger(__name__).warning("User action required: %s; scope=%s; %s",
                                            reason, key, ACTION_INSTRUCTIONS[reason])


def action_summary(outcome: RunOutcome) -> str:
    """Build external text from fixed codes and counts only."""
    return "\n".join(f"- {reason} ({len(keys)}): {ACTION_INSTRUCTIONS[reason]}"
                     for reason, keys in sorted(outcome["actions"].items())
                     if reason in ACTION_INSTRUCTIONS and keys)
