"""Run-local failures and delivery bookkeeping; external summaries use fixed codes."""

import logging
from typing import TYPE_CHECKING, NotRequired, TypedDict

import requests

if TYPE_CHECKING:
    from ghostfolio_ibkr_sync.corporate_actions import NotificationPlan


class Failure(TypedDict):
    stage: str
    reason: str
    ordinal: int | None


class AccountResult(TypedDict):
    simulated: bool
    accepted: int | None
    duplicates: int | None
    held: set[str] | None
    deferred: set[str] | None
    cash: str


class RunOutcome(TypedDict):
    account_results: dict[str, AccountResult]
    actions: dict[str, set[str]]
    failures: list[Failure]
    dropped: int
    accounts_total: int
    accounts_failed: int
    token_expiry_days: NotRequired[int]
    forced_preview: NotRequired[str]
    corporate_notification: NotRequired[NotificationPlan]
    corporate_maintenance: NotRequired[bool]
    delivery: NotRequired[str]
    review_held: NotRequired[set[str]]
    deferred: NotRequired[set[str]]


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
    return {"account_results": {}, "actions": {}, "failures": [], "dropped": 0, "accounts_total": 0, "accounts_failed": 0}


def record_failure(outcome: RunOutcome, stage: str, reason: str, ordinal: object = None) -> None:
    """Record one failure; unknown codes collapse to unexpected/unhandled_error."""
    if reason not in OUTCOME_REASONS.get(stage, ()):
        stage, reason = "unexpected", "unhandled_error"
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1:
        ordinal = None
    record_action(outcome, "processing_failure", f"{stage}:{ordinal}")
    if len(outcome["failures"]) >= MAX_OUTCOME_FAILURES:
        outcome["dropped"] += 1
        return
    outcome["failures"].append({"stage": stage, "reason": reason, "ordinal": ordinal})


# Private event keys never enter external summaries. Instructions and resolution
# proof are fixed text; callers supply only the observed code and private scope.
ACTION_INSTRUCTIONS = {
    "processing_failure": "Inspect the fixed failure reason and private configuration or service log. Preserve financial recovery fences and verify uncertain requests before any resend. Resolution: current prerequisite and processing evidence pass.",
    "cash_missing": "Inspect the Flex cash report configuration. Cash was not updated. Resolution: the current report supplies a valid BASE_SUMMARY and base currency.",
    "corporate_action": "Inspect the corporate-action conclusions and restore the stated evidence or state. Holds require fresh source and destination agreement; acknowledgment or state reset cannot release them. Resolution: current conclusions prove safe continuation or the historical discrepancy is resolved.",
    "token_renewal": "Regenerate GHOST_TOKEN or switch to GHOST_ACCESS_TOKEN. Resolution: a current credential is outside the configured expiry warning window.",
    "timezone_correction": "Set TZ to the intended valid IANA timezone. Resolution: the next run validates TZ; simulation alone does not correct it.",
    "dividend_rejected": "Inspect the rejected payable event and missing or conflicting Flex quantity, cash or tax evidence. Never invent payment or quantity. Resolution: complete consistent current source evidence supports the event.",
    "dividend_reversal": "Compare the reversal with the original dividend in Ghostfolio and preserved Flex cash rows. Do not resend. Resolution: source and destination prove the reversal outcome or documented manual resolution.",
    "dividend_signed_tax": "Inspect signed withholding, refunds and orphan tax against the original payment in Ghostfolio. Do not invent or resend a transaction. Resolution: current payment and tax evidence reconcile or documented manual resolution.",
    "trade_invalid": "Inspect the omitted trade and required Flex fields. Do not invent a trade. Resolution: valid current source evidence permits safe conversion.",
    "trade_manual": "Compare the source trade with the manual Ghostfolio activity before any reference repair. Resolution: verified reference ownership or documented manual resolution.",
    "trade_position": "Compare current Ghostfolio holdings and source trades. Resolution: verified holdings support the intended sale; no automatic repair is authorized.",
    "mapping_conflict": "Inspect the different-symbol holding in Ghostfolio and MAPPING_FILE. Resolution: the intended security and holding use a verified explicit mapping.",
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


def log_operational_result(outcome: RunOutcome, code: int) -> None:
    """Report only observed acceptance evidence; never imply balance readback."""
    log = logging.getLogger(__name__)
    result = "failure" if code else "success with user action required" if outcome["actions"] else "success"
    level = logging.ERROR if code else logging.WARNING if outcome["actions"] else logging.INFO
    held = outcome.get("review_held")
    deferred = outcome.get("deferred")
    log.log(level, "Cycle result: %s; unique review-held events=%s; deferred automatic work=%s; notification=%s; "
            "decision counts can overlap", result, len(held) if held is not None else "unavailable",
            len(deferred) if deferred is not None else "unavailable", outcome.get("delivery", "unavailable"))
    if not outcome["account_results"]:
        log.info("Account evidence: imports=unavailable; duplicates=unavailable; cash=unavailable")
    for key, account in outcome["account_results"].items():
        log.info("Account evidence %s: %s=%s; duplicates=%s; other held events=%s; "
                 "deferred automatic work=%s; cash=%s", key,
                 "simulated proposals" if account["simulated"] else "accepted imports",
                 account["accepted"] if account["accepted"] is not None else "unavailable",
                 account["duplicates"] if account["duplicates"] is not None else "unavailable",
                 len(account["held"]) if account["held"] is not None else "unavailable",
                 len(account["deferred"]) if account["deferred"] is not None else "unavailable", account["cash"])
