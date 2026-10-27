"""Run orchestration: account processing, finalization and the sync entry point."""

import base64
import json
import logging
import os
import re
import time
from collections.abc import Callable, Mapping
from copy import deepcopy
from math import ceil, isfinite
from pathlib import Path
from typing import Any, cast
from xml.etree.ElementTree import ParseError

import requests

from ghostfolio_ibkr_sync import corporate_actions as ca
from ghostfolio_ibkr_sync.activity_review import (
    ReviewState,
    assert_unchanged,
    close_review,
    open_review,
    process_review,
    source_events,
)
from ghostfolio_ibkr_sync.config import (
    dry_run_requested,
    load_config,
    load_notification_delivery,
    timezone_preview_reason,
)
from ghostfolio_ibkr_sync.diagnostics import (
    historical_dividend_comparison,
    log_historical_dividend_comparison,
)
from ghostfolio_ibkr_sync.ghostfolio import (
    InvalidActivityIdentityError,
    activity_date_is_current,
    dividend_context,
    format_versioned_activity_identity,
    ghost_corporate_evidence,
    ghost_exchange_access_token,
    ghost_find_account_id,
    ghost_get_existing_orders,
    ghost_import_activities,
    ghost_update_cash_balance,
    parse_versioned_activity_identity,
)
from ghostfolio_ibkr_sync.ibkr import (
    SKIP_ASSET_CATEGORIES,
    dividend_field_prerequisites,
    dividend_input_compatible,
    fetch_flex_report,
    flex_provenance_failures,
    historical_dividend_report_window,
    parse_base_currency,
    parse_cash_dividends,
    parse_cash_report,
    parse_source_account_ids,
    parse_trades,
)
from ghostfolio_ibkr_sync.models import DividendContext
from ghostfolio_ibkr_sync.notify import (
    FORCED_PREVIEW_NOTIFY_TITLE,
    NOTIFY_TITLE,
    TOKEN_EXPIRY_NOTIFY_TITLE,
    build_failure_summary,
    build_forced_preview_summary,
    build_token_expiry_summary,
    send_notification,
)
from ghostfolio_ibkr_sync.outcome import (
    RunOutcome,
    action_summary,
    is_token_rejection,
    new_run_outcome,
    record_failure,
)
from ghostfolio_ibkr_sync.sync import (
    Activity,
    DividendEntry,
    Positions,
    Unmapped,
    convert_dividend_actions,
    convert_dividend_to_activity,
    convert_trade_to_activity,
    dividend_dedup_decision,
    filter_trades_by_holdings,
    load_mapping,
    log_dividend_proximity_skip,
    rejected_sell_symbols,
    resolve_symbol,
    split_import_phases,
    trade_id_decision,
    unique_trades,
)

log = logging.getLogger(__name__)


def legacy_token_expiry_days(config: dict[str, Any], now: float | None = None) -> int | None:
    """Read an unverified JWT expiry for reminders only, never authentication."""
    if config.get("ghost_access_token") is not None:
        return None
    raw_days = os.environ.get("GHOST_TOKEN_EXPIRY_WARNING_DAYS", "14").strip()
    if not re.fullmatch(r"[0-9]{1,3}", raw_days) or int(raw_days) > 365:
        log.warning("GHOST_TOKEN_EXPIRY_WARNING_DAYS is invalid; using 14 days")
        raw_days = "14"
    warning_days = int(raw_days)
    if warning_days == 0:
        return None
    try:
        token = config.get("ghost_token")
        if not isinstance(token, str) or len(token) > 16384:
            raise ValueError
        parts = token.split(".")
        if (len(parts) != 3 or not parts[0] or not parts[2]
                or not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", parts[1])):
            raise ValueError
        payload = json.loads(base64.b64decode(
            parts[1] + "=" * (-len(parts[1]) % 4), altchars=b"-_", validate=True))
        expiry: Any = payload.get("exp") if isinstance(payload, dict) else None
        if type(expiry) not in (int, float) or not isfinite(expiry):
            raise ValueError
        seconds_left = expiry - (time.time() if now is None else now)
        if seconds_left > warning_days * 86400:
            return None
        return cast(int, max(0, ceil(seconds_left / 86400)))
    except (ValueError, OverflowError, RecursionError):
        log.debug("Legacy GHOST_TOKEN has no usable JWT expiry; reminder skipped")
        return None


def process_account(config: dict[str, Any], ibkr_account_id: str, query_id: str,
                    ghost_account_name: str, mapping: dict[str, str],
                    existing_trade_ids: set[str], existing_dividend_comments: set[tuple[str, str]],
                    positions: Positions) -> tuple[Unmapped, bool]:
    """Process a single IBKR account: fetch, parse, and sync to Ghostfolio.

    The two existing_* sets are shared across accounts and updated in place with
    whatever this account imports, so a later account will not re-import them.

    Returns a tuple of (unmapped, ok) where ok is False if any step failed.
    """
    log.info("Processing IBKR account %s (Ghostfolio: %s)", ibkr_account_id, ghost_account_name)
    ok = True

    # Fetch the Flex Query report
    try:
        if "_source_reports" in config:
            xml_text = config["_source_reports"].get((ibkr_account_id, query_id))
            if xml_text is None:
                raise RuntimeError("Source acquisition failed")
        elif "_review_reports" in config:
            xml_text = config["_review_reports"].get(ibkr_account_id)
            if xml_text is None:
                raise RuntimeError("Review source acquisition failed")
        else:
            xml_text = fetch_flex_report(config["ibkr_token"], query_id)
    except Exception as exc:
        log.error("Failed to fetch Flex Query for account %s: %s", ibkr_account_id, exc)
        return {}, False

    source_account_ids = parse_source_account_ids(xml_text)
    if source_account_ids != {ibkr_account_id}:
        if source_account_ids is None:
            reason = "missing"
        elif len(source_account_ids) > 1:
            reason = "mixed"
        else:
            reason = "mismatched"
        log.error("Flex Query %s source account evidence is %s; account failed before "
                  "Ghostfolio lookup or any write", query_id, reason)
        return {}, False

    if ((ibkr_account_id, query_id) in config.get("_source_failed", set())
            or (config.get("_review_state") is not None
                and ibkr_account_id in config.get("_review_failed_sources", set()))):
        return {}, False
    if config.get("_review_state") is not None:
        assert_unchanged(config["_review_state"])

    # Find the Ghostfolio account
    try:
        ghost_account_id = (config["_source_accounts"].get((ibkr_account_id, query_id))
                            if "_source_accounts" in config
                            else ghost_find_account_id(config, ghost_account_name))
    except (requests.RequestException, RuntimeError) as exc:
        log.error("Failed to look up Ghostfolio account '%s': %s", ghost_account_name, exc)
        return {}, False
    if ghost_account_id is None:
        return {}, False

    if ghost_account_id in config.get("_uncertain_import_accounts", set()):
        log.error("Account %s has an uncertain earlier import outcome; refusing further writes", ghost_account_id)
        return {}, False

    if ghost_account_id in config.get("_review_blocked_accounts", set()):
        log.error("Account %s has a correction failure; all financial writes blocked", ghost_account_id)
        return {}, False

    # Flex provenance is a prerequisite: fail before any import, cash or platform write
    provenance = flex_provenance_failures(xml_text)
    if provenance:
        log.error("Flex Query %s: cash rows without a valid 'YYYYMMDD;HHmmss TimeZone' dateTime "
                  "(%s); account failed before any write. Add Date/Time with time zone to the "
                  "query, see README", query_id,
                  ", ".join(f"{kind}: {count}" for kind, count in sorted(provenance.items())))
        return {}, False

    # Required dividend fields are a prerequisite too, even with no new dividend
    gaps = dividend_field_prerequisites(xml_text)
    if gaps:
        log.error("Flex Query %s: required dividend fields missing from the report (%s); account "
                  "failed before any write. Tick these fields in the query, see README",
                  query_id, ", ".join(gaps))
        return {}, False

    try:
        activities, proposed_dividend_context, unmapped, selection_ok = select_account_activities(
            xml_text, ibkr_account_id, ghost_account_id, mapping, existing_trade_ids,
            existing_dividend_comments, positions, query_id=query_id,
            diagnostic_preview=bool(config.get("dry_run")),
            review_holds=config.get("_review_holds"),
            corporate_decision=config.get("_corporate_decisions", {}).get(ibkr_account_id))
    except InvalidActivityIdentityError:
        return {}, False
    ok = ok and selection_ok
    decision = config.get("_corporate_decisions", {}).get(ibkr_account_id)
    if decision is not None:
        ok = ok and not decision["account_held"] and not decision["symbols"]

    # Create buys/dividends first. A server-skipped BUY cannot back a later SELL,
    # even in this account's batch. Dry-run uses proposed buys for simulation.
    phases = split_import_phases(activities)
    for phase in phases:
        if not phase:
            continue
        if ghost_account_id in config.get("_uncertain_import_accounts", set()):
            ok = False
            break
        if phase[0]["type"] == "SELL":
            rejected = rejected_sell_symbols(phase, positions, ghost_account_id)
            if rejected:
                log.warning("Sells excluded after accepted-buy check: %s", ", ".join(sorted(rejected)))
                phase = [a for a in phase if a["symbol"] not in rejected]
                ok = False
        if not phase:
            continue
        imported, import_ok = ghost_import_activities(config, phase)
        # Only accepted rows (or proposals in isolated simulation state) advance
        # the run. DIVIDEND identities must never act as trade IDs or holdings.
        record_accepted_activities(imported, positions, existing_trade_ids,
                                   existing_dividend_comments, proposed_dividend_context)
        if not import_ok:
            ok = False

    # Update cash balance (independent of import success)
    try:
        cash_balance = parse_cash_report(xml_text)
        if cash_balance is not None:
            if not ghost_update_cash_balance(config, ghost_account_id, cash_balance,
                                         parse_base_currency(xml_text)):
                ok = False
        else:
            log.warning("No BASE_SUMMARY cash balance found in report")
    except Exception as exc:
        log.error("Failed to update cash balance: %s", exc)
        ok = False

    return unmapped, ok


def select_account_activities(
    xml_text: str, ibkr_account_id: str, ghost_account_id: str,
    mapping: dict[str, str], existing_trade_ids: set[str],
    existing_dividend_comments: set[tuple[str, str]], positions: Positions, *,
    query_id: str = "offline", diagnostic_preview: bool = False,
    date_is_current: Callable[[Mapping[str, Any]], bool] | None = None,
    holdings_trace: dict[str, Any] | None = None,
    review_holds: set[str] | None = None,
    corporate_decision: ca.Decision | None = None,
) -> tuple[list[Activity], dict[str, DividendContext], Unmapped, bool]:
    """Select without fetching or dispatching; mutate only manual-match state.

    Offline callers supply a captured clock and isolated holdings state.
    """
    ok = True
    review_holds = review_holds or set()
    date_is_current = date_is_current or activity_date_is_current
    # Parse trades and dividends
    trades: list[dict[str, Any]] = parse_trades(xml_text)
    dividends = parse_cash_dividends(xml_text)
    if dividends is None:
        log.error("Flex Query %s has no Cash Transactions section: dividends not synced. "
                  "Add Cash Transactions (Dividends, Payment In Lieu Of Dividends, "
                  "Withholding Tax) to the query, see README", query_id)
        ok = False
        dividends = []
    log.debug("Found %d trades and %d dividend payments in Flex Query report",
              len(trades), len(dividends))

    # CASH (FX conversions) and OPT are never imported; drop them before any gate
    trades = [t for t in trades if t.get("assetCategory", "") not in SKIP_ASSET_CATEGORIES]

    # Validate the complete trade set before deduplication, holdings or any write.
    # A bad later row must not allow earlier valid imports or independent cash.
    try:
        format_versioned_activity_identity(ibkr_account_id, "TRADE", "0")
        for trade in trades:
            if trade.get("accountId", "") != ibkr_account_id:
                raise InvalidActivityIdentityError("Trade account differs from verified report account")
            format_versioned_activity_identity(ibkr_account_id, "TRADE", trade.get("tradeID", ""))
    except InvalidActivityIdentityError as exc:
        log.error("Flex Query %s: %s; account failed before any financial write", query_id, exc)
        raise

    # Prepare actual import candidates before calculating their position impact.
    unmapped: Unmapped = {}
    prepared_trades: list[dict[str, Any]] = []
    skipped_other = 0

    unique, skipped_dup, conflicts = unique_trades(trades)
    if conflicts:
        log.error("Conflicting repeated trade IDs excluded: %s", ", ".join(sorted(conflicts)))
        ok = False

    for trade in unique:
        trade_id = trade.get("tradeID", "")
        if format_versioned_activity_identity(ibkr_account_id, "TRADE", trade_id) in review_holds:
            continue
        decision = trade_id_decision(
            trade_id, ibkr_account_id, conflicts, existing_trade_ids, positions,
        )
        if decision == "missing":
            log.warning("Skipping trade for %s (%s) — missing tradeID, cannot deduplicate safely",
                        trade.get("symbol") or trade.get("isin") or "unknown",
                        trade.get("dateTime", ""))
            skipped_other += 1
            ok = False
            continue
        if decision == "conflict":
            skipped_other += 1
            continue
        if decision == "existing":
            skipped_dup += 1
            continue

        trade_unmapped: Unmapped = {}
        activity = convert_trade_to_activity(trade, ghost_account_id, mapping, trade_unmapped)
        if activity is None or not date_is_current(activity) or not all(isfinite(activity[field]) for field in ("quantity", "unitPrice", "fee")):
            log.error("Trade %s cannot be converted safely; excluded before holdings checks", trade_id)
            skipped_other += 1
            ok = False
            continue
        if corporate_decision is not None and ca.candidate_held(corporate_decision, activity):
            log.warning("Corporate-action BUY/SELL candidate held for %s", activity["symbol"])
            ok = False
            continue
        # The gate must use the same signed quantity the converted BUY/SELL will
        # add to Ghostfolio, while retaining raw fields for manual-entry matching.
        prepared_trades.append({**trade,
                                "quantity": (-1 if activity["type"] == "SELL" else 1) * activity["quantity"],
                                "_activity": activity, "_unmapped": trade_unmapped})

    trades = filter_trades_by_holdings(prepared_trades, positions, ghost_account_id, mapping,
                                      existing_trade_ids, source_account=ibkr_account_id)
    activities: list[Activity] = []
    for kept in trades:
        activities.append(kept["_activity"])
        unmapped.update(kept["_unmapped"])

    log.info("New trade activities: %d, duplicates skipped: %d, other skipped: %d",
             len(activities), skipped_dup, skipped_other)

    # Establish identity and deduplicate before checking quantity or schema.
    report_counts = None
    if diagnostic_preview:
        findings = historical_dividend_comparison(dividends, ghost_account_id, mapping, positions,
                                                 historical_dividend_report_window(xml_text),
                                                 existing_dividend_comments)
        report_counts = log_historical_dividend_comparison(findings, ghost_account_id)
    div_activities: list[Activity] = []
    proposed_dividend_context: dict[str, DividendContext] = {}
    div_skipped_dup = 0
    candidates = []
    for div in dividends:
        if any(format_versioned_activity_identity(ibkr_account_id, "DIVIDEND", row.get("actionID", ""))
               in review_holds for row in div["payments"]):
            continue
        dedup, symbol, matched = dividend_dedup_decision(
            div, ghost_account_id, mapping, positions, existing_dividend_comments)
        if dedup == "not_payable":
            # Preserve existing diagnostics for reversals and tax-only rows.
            convert_dividend_to_activity(div, ghost_account_id, mapping, unmapped)
            continue
        if dedup == "existing":
            div_skipped_dup += 1
            continue
        if dedup == "partial":
            log.error("Dividend %s %s: partial versioned action coverage — not imported; "
                      "account failed; automatic reruns will refuse while this group stays "
                      "in the report window; explicit reviewed recovery required",
                      symbol or div.get("symbol") or "unknown", div["date"])
            ok = False
            continue
        if dedup == "action_conflict":
            log.error("Dividend %s %s: versioned action-context conflict or unknown overlap — "
                      "not imported; account failed; manual review required",
                      symbol or div.get("symbol") or "unknown", div["date"])
            ok = False
            continue
        if dedup == "proximity":
            log_dividend_proximity_skip(cast(str, symbol), div, cast(DividendEntry, matched))
            div_skipped_dup += 1
            continue
        candidates.append(div)

    # Validate all new identity segments before dispatch or independent cash.
    try:
        for div in candidates:
            for row in div["payments"]:
                if row.get("accountId", "") != ibkr_account_id:
                    raise InvalidActivityIdentityError(
                        "Dividend account differs from verified report account")
                format_versioned_activity_identity(
                    ibkr_account_id, "DIVIDEND", row.get("actionID", ""))
    except InvalidActivityIdentityError as exc:
        log.error("Flex Query %s: %s; account failed before any financial write", query_id, exc)
        raise

    # A schema mismatch blocks only account dividends, not trades or cash.
    if dividend_input_compatible(candidates):
        for div in candidates:
            proposed, partition_ok = convert_dividend_actions(
                div, ghost_account_id, mapping, unmapped, dividends)
            if not partition_ok:
                ok = False
                continue
            if any(not date_is_current(activity) for activity in proposed):
                log.error("Future or invalid dividend date; deferred until a later run")
                ok = False
                continue
            div_activities.extend(proposed)
            for activity in proposed:
                proposed_dividend_context[activity["comment"]] = dividend_context(
                    {**activity, "isin": div["isin"]}, activity["date"])

    if report_counts is None:
        log.info("New dividend activities: %d, duplicates skipped: %d",
                 len(div_activities), div_skipped_dup)
    else:
        log.info("New dividend activities: %d, duplicates skipped: %d; dividend report: "
                 "%d to check, %d informational, %d noise",
                 len(div_activities), div_skipped_dup, report_counts["to_check"],
                 report_counts["informational"], report_counts["noise"])

    activities.extend(div_activities)
    if holdings_trace is not None:
        holdings_trace.update({
            "prepared": [t["_activity"] for t in prepared_trades],
            "kept": [t["_activity"] for t in trades],
            "manual_trade_ids": sorted(positions.get("manual_trade_ids", set())),
        })
    return activities, proposed_dividend_context, unmapped, ok


def record_accepted_activities(
    imported: list[Activity], positions: Positions, existing_trade_ids: set[str],
    existing_dividend_comments: set[tuple[str, str]],
    proposed_dividend_context: dict[str, DividendContext],
) -> None:
    """Advance only supplied accepted (or isolated simulated) payload state."""
    for activity in imported:
        comment = activity["comment"]
        identity = parse_versioned_activity_identity(comment, activity["type"])
        if identity is not None:
            comment = comment.split("\n", 1)[0]
            positions["versioned_identities"].add((identity[0], comment))
            if identity[1] == "DIVIDEND":
                positions.setdefault("versioned_dividend_context", {}).setdefault(
                    (identity[0], comment), []).append(proposed_dividend_context[comment])
            if identity[1] == "TRADE":
                sign = -1.0 if activity["type"] == "SELL" else 1.0
                positions["qty"][(activity["accountId"], activity["symbol"])] += sign * activity["quantity"]
        elif comment.startswith("IBKR#"):
            existing_trade_ids.add(comment.split("#", 1)[1])
            sign = -1.0 if activity["type"] == "SELL" else 1.0
            positions["qty"][(activity["accountId"], activity["symbol"])] += sign * activity["quantity"]
        elif comment.startswith("dividend#"):
            existing_dividend_comments.add((activity["accountId"], comment))



def report_delivery(outcome: RunOutcome, status: str) -> None:
    """Log one fixed transport result; never retry or change financial status."""
    outcome["delivery"] = status
    warning = status not in ("sent", "not required")
    log.log(logging.WARNING if warning else logging.INFO, "Notification result: %s%s", status,
            "; inspect APPRISE_URLS/APPRISE_TIMEOUT and the local log" if warning else "")


def finalize_run(outcome: RunOutcome, code: int) -> None:
    """Send at most one notification for failures or a legacy-token reminder.

    Ordinary warnings and successful simulations remain silent. Failures
    notify in every mode, including invalid configuration. Delivery never changes
    the exit code. A reminder on a failed run joins its failure notification.
    """
    actions = action_summary(outcome)
    days = outcome.get("token_expiry_days")
    preview = outcome.get("forced_preview")
    corporate = outcome.get("corporate_notification")
    corporate_due = corporate is not None and bool(corporate["sent"])
    maintenance_due = outcome.get("corporate_maintenance", False)
    if code == 0 and not actions and not corporate_due and not maintenance_due and (dry_run_requested() or (days is None and not preview)):
        report_delivery(outcome, "not required")
        return
    label = "Failure" if code else ("Corporate actions" if corporate_due or maintenance_due else
                                   ("Forced preview" if preview else "Token expiry"))
    try:
        settings, configuration = load_notification_delivery()
        if settings is None:
            report_delivery(outcome, configuration)
            return
        if code:
            title, body = NOTIFY_TITLE, build_failure_summary(outcome)
        elif corporate_due or maintenance_due:
            title, body = "ghostfolio-ibkr-sync: corporate actions", "Corporate-action evidence summary."
            if not dry_run_requested():
                if preview:
                    body += "\n" + build_forced_preview_summary(preview)
                if days is not None:
                    body += "\n" + build_token_expiry_summary(days)
        elif actions:
            title, body = "ghostfolio-ibkr-sync: user action required", "User action required."
        elif preview:
            title, body = FORCED_PREVIEW_NOTIFY_TITLE, build_forced_preview_summary(preview)
            if days is not None:
                body += "\n" + build_token_expiry_summary(days)
        else:
            title, body = TOKEN_EXPIRY_NOTIFY_TITLE, build_token_expiry_summary(cast(int, days))
        if corporate_due and corporate is not None:
            body += "\n" + "\n".join(f"- corporate_actions: {key} ({value})"
                                       for key, value in corporate["counts"].items()
                                       if key in ("active_holds", "changed_findings", "resumptions") and type(value) is int)
        if maintenance_due:
            body += "\n- corporate_actions: maintenance_incomplete (1)"
        if actions:
            body += "\n" + actions
        status = send_notification(settings, title, body)
    except Exception:
        log.warning("%s notification could not be sent: internal error", label)
        report_delivery(outcome, "failed")
        return
    delivery = {"sent": "sent", "timeout": "timeout, delivery unconfirmed",
                "invalid_destination": "invalid configuration"}.get(status, "failed")
    report_delivery(outcome, delivery)
    if status == "sent":
        if corporate_due and corporate is not None:
            ca.confirm_notification(cast(ca.NotificationPlan, corporate))
        log.info("%s notification sent", label)
    elif status == "timeout":
        log.warning("%s notification timed out (it may still arrive; not retried)", label)
    else:
        log.warning("%s notification not delivered: %s", label, delivery)


def run_sync(outcome: RunOutcome) -> int:
    """Run one sync.  Returns the exit code; every exit 1 is recorded in outcome."""
    try:
        config = cast(dict[str, Any], load_config())
    except RuntimeError as exc:
        log.error("Configuration error: %s", exc)
        record_failure(outcome, "config", "invalid_configuration")
        return 1
    state: ReviewState | None = None
    try:
        if config.get("activity_review_file"):
            try:
                state = open_review(config["activity_review_file"], [config["mapping_file"]])
            except (RuntimeError, OSError) as exc:
                log.error("Review prerequisite failed: %s", exc)
                record_failure(outcome, "review", "review_unavailable")
                return 1
            config["_review_state"] = state
        return run_configured_sync(config, outcome)
    finally:
        if state is not None:
            close_review(state)


def prepare_review_sources(config: dict[str, Any], mapping: dict[str, str], names: list[str]) -> None:
    """Acquire before target lookup; retain independent source failures."""
    reports: dict[str, str | None] = {}
    events: dict[str, dict[str, Any]] = {}
    accounts: dict[str, str] = {}
    failed: set[str] = set()
    source_reports: dict[tuple[str, str], str | None] = {}
    source_accounts: dict[tuple[str, str], str] = {}
    source_failed: set[tuple[str, str]] = set()
    for source, query, name in zip(config["account_ids"], config["query_ids"], names, strict=True):
        try:
            xml = fetch_flex_report(config["ibkr_token"], query)
            if parse_source_account_ids(xml) != {source}:
                raise RuntimeError("Source account mismatch")
            ca.parse_report(config.get("_corporate_store"), xml, source)  # Validate before target lookup.
            reports[source] = xml
            target = ghost_find_account_id(config, name)
            if target is None:
                raise RuntimeError("Destination account missing")
            accounts[source] = target
            source_accounts[(source, query)] = target
            source_reports[(source, query)] = xml
            if config.get("_review_state") is not None:
                events.update(source_events(xml, source, target, mapping))
        except Exception:
            reports[source] = None
            failed.add(source)
            source_reports[(source, query)] = None
            source_failed.add((source, query))
            log.error("Source report acquisition/validation failed for source account %s", source)
    for item in (config.get("_review_state") or {"document": {"proposals": {}}})["document"]["proposals"].values():
        source = item.get("source account")
        target = item.get("destination account")
        if (isinstance(source, str) and source in failed and source not in accounts
                and isinstance(target, str) and target):
            accounts[source] = target
    # Retained bindings can suspend failed sources, never authorize dispatch.
    config["_source_reports"] = source_reports
    config["_source_accounts"] = source_accounts
    config["_source_failed"] = source_failed
    config["_review_reports"] = reports
    config["_review_events"] = events
    config["_review_accounts"] = accounts
    config["_review_failed_sources"] = failed


def run_configured_sync(config: dict[str, Any], outcome: RunOutcome) -> int:
    """Own the corporate-action lock for this run, including simulation."""
    store: ca.Store | None = None
    try:
        inputs = [config.get("mapping_file", ""), config.get("corporate_action_evidence_file", "")]
        if config.get("activity_review_file"):
            inputs += [config["activity_review_file"], config["activity_review_file"] + ".journal.yaml",
                       config["activity_review_file"] + ".lock"]
        try:
            store = ca.open_store(config.get("corporate_action_state_file",
                                             os.environ.get("CORPORATE_ACTION_STATE_FILE")) or "",
                                  inputs, simulation=bool(config["dry_run"] or timezone_preview_reason()))
            config["_corporate_store"] = store
        except (RuntimeError, OSError):
            log.error("Corporate-action state unavailable; BUY/SELL held; cash keeps existing guards")
        config["_corporate_outcome"] = outcome
        return _run_configured_sync(config, outcome)
    finally:
        config.pop("_corporate_store", None)
        if store is not None:
            ca.close_store(store)


def _run_configured_sync(config: dict[str, Any], outcome: RunOutcome) -> int:
    """Execute with any optional persistent-review lock held for the whole run."""
    reason = timezone_preview_reason()
    if reason:
        config["dry_run"] = True
        outcome["forced_preview"] = reason
        log.warning("%s: whole run forced to DRY_RUN, no Ghostfolio writes", reason)
    if config["dry_run"]:
        log.info("DRY RUN enabled (DRY_RUN) — no writes will be sent to Ghostfolio")
    try:
        mapping = load_mapping(config["mapping_file"])
    except RuntimeError as exc:
        log.error("%s", exc)
        record_failure(outcome, "mapping", "invalid_mapping")
        return 1
    log.info("Loaded %d symbol mappings", len(mapping))

    days = legacy_token_expiry_days(config)
    if days is not None:
        outcome["token_expiry_days"] = days
        if days:
            log.warning("Legacy GHOST_TOKEN expires in %d day(s); regenerate it or "
                        "switch to GHOST_ACCESS_TOKEN", days)
        else:
            log.warning("Legacy GHOST_TOKEN has expired; regenerate it or "
                        "switch to GHOST_ACCESS_TOKEN")

    # Access mode: one fresh bearer per run, after local validation and before
    # any Ghostfolio or IBKR call (dry-run included: a login writes nothing).
    # Never re-authenticated mid-run.
    if config.get("ghost_access_token") is not None:
        try:
            config["ghost_token"] = ghost_exchange_access_token(
                config["ghost_host"], config.pop("ghost_access_token"))
        except RuntimeError as exc:
            log.error("%s", exc)
            record_failure(outcome, "ghost_auth", "login_failed")
            return 1
        log.info("Authenticated to Ghostfolio with GHOST_ACCESS_TOKEN")

    account_ids = config["account_ids"]
    query_ids = config["query_ids"]
    account_names = config["account_names"]

    # If no account names provided, use account IDs as names
    if not account_names:
        account_names = account_ids
        log.warning("No GHOST_ACCOUNT_NAMES provided, using IBKR account IDs as Ghostfolio account names")

    prepare_review_sources(config, mapping, account_names)

    # Fetch existing activities once for the whole run; process_account keeps the
    # sets current as it imports
    try:
        existing_trade_ids, existing_dividend_comments, positions = ghost_get_existing_orders(config)
    except InvalidActivityIdentityError:
        log.error("Ghostfolio has an invalid reserved activity identity; refusing to sync")
        record_failure(outcome, "ghost_startup", "invalid_identity")
        return 1
    except (requests.RequestException, RuntimeError) as exc:
        log.error("Failed to fetch existing Ghostfolio activities: %s", exc)
        if is_token_rejection(exc):
            log.error("Ghostfolio rejected the token: an expired GHOST_TOKEN must be "
                      "regenerated, or switch to GHOST_ACCESS_TOKEN")
            record_failure(outcome, "ghost_startup", "token_rejected")
        else:
            record_failure(outcome, "ghost_startup", "activities_unavailable")
        return 1
    log.info("Found %d existing trade activities, %d existing dividend activities and "
             "%d versioned identities in Ghostfolio",
             len(existing_trade_ids), len(existing_dividend_comments),
             len(positions.get("versioned_identities", set())))

    # Reparse retained bytes and reconcile before review can dispatch any PUT.
    def reconcile_corporate(rows: list[dict[str, Any]] | None = None) -> None:
        snapshot = ({"activities": rows, "count": len(rows)} if rows is not None
                    else positions.get("corporate_snapshot"))
        refresh_corporate_decisions(config, mapping, snapshot, positions)

    config["_corporate_reconcile"] = reconcile_corporate
    reconcile_corporate()

    if (config.get("_review_state") is not None
            and (any(xml is not None for xml in config["_review_reports"].values())
                 or config["_review_state"]["original"] is not None
                 or config["_review_state"]["journal_original"] is not None)):
        try:
            blocked, held = process_review(config["_review_state"], config,
                                           config["_review_events"], config["_review_accounts"])
        except (RuntimeError, OSError) as exc:
            log.error("Review prerequisite failed: %s", exc)
            record_failure(outcome, "review", "review_unavailable")
            return 1
        config["_review_blocked_accounts"], config["_review_holds"] = blocked, held
        # A replacement changes positions once. Never add its full quantity to
        # the earlier holdings. Rebuild every account from verified destination.
        existing_trade_ids, existing_dividend_comments, positions = ghost_get_existing_orders(config)
        reconcile_corporate()

    all_unmapped = {}
    failed_accounts = []
    outcome["accounts_total"] = len(account_ids)

    if config.get("dry_run"):
        # Share proposals across simulated queries without changing the snapshot.
        existing_trade_ids = existing_trade_ids.copy()
        existing_dividend_comments = existing_dividend_comments.copy()
        positions = deepcopy(positions)

    for ordinal, (ibkr_id, qid, gf_name) in enumerate(zip(account_ids, query_ids, account_names), 1):  # noqa: B905
        # process_account handles the failures it expects; an unforeseen error in one
        # account must cost that account, not the accounts still to be processed
        reason = "account_failed"
        try:
            unmapped, ok = process_account(config, ibkr_id, qid, gf_name, mapping,
                                           existing_trade_ids, existing_dividend_comments, positions)
        except Exception:
            log.exception("Unexpected error while processing IBKR account %s", ibkr_id)
            unmapped, ok, reason = {}, False, "unexpected_error"
        all_unmapped.update(unmapped)
        if not ok:
            failed_accounts.append(ibkr_id)
            outcome["accounts_failed"] += 1
            record_failure(outcome, "account", reason, ordinal)

    # Log unmapped ISINs: one self-contained line per ISIN so each survives line-based log viewers.
    # Trades are reported only on their import run (deduped before conversion);
    # dividends are converted before dedup, so they repeat on every run.
    for isin, info in sorted(all_unmapped.items()):
        symbol = info.get("symbol") or ""
        desc = info.get("description") or ""
        log.warning("Unmapped ISIN %s (%s) uses IBKR symbol %r as ticker (fallback) — "
                    "verify in Ghostfolio or add to mapping symbol_mapping: '%s: <yahoo ticker>'",
                    isin, desc or "no description", symbol, isin)
    if not all_unmapped:
        log.info("No unmapped ISINs in this run")

    corporate_failed = any(d["account_held"] or d["symbols"]
                           for d in config.get("_corporate_decisions", {}).values())
    if corporate_failed:
        record_failure(outcome, "corporate_actions", "trade_hold")
    if failed_accounts or corporate_failed:
        log.error("Sync completed with errors for %d of %d account(s): %s",
                  len(failed_accounts), len(account_ids), ", ".join(failed_accounts))
        return 1

    log.info("Sync complete")
    return 0


def main() -> int:
    """Main entry point.  Returns a process exit code (0 = clean, 1 = failure).

    SystemExit and KeyboardInterrupt propagate untouched: an interrupted run is
    not a completed run and sends no notification.
    """
    log.info("Starting IBKR to Ghostfolio sync (version %s)", os.environ.get("APP_VERSION", "dev"))
    if not os.environ.get("DRY_RUN", "").strip():
        log.warning("DRY_RUN not set: simulation, nothing written")
    outcome = new_run_outcome()
    try:
        code = run_sync(outcome)
    except Exception:
        log.exception("Sync failed with an unhandled error")
        record_failure(outcome, "unexpected", "unhandled_error")
        code = 1
    finalize_run(outcome, code)
    return code


def refresh_corporate_decisions(config: dict[str, Any], mapping: dict[str, str],
                                snapshot: dict[str, Any] | None, positions: Positions) -> None:
    """Compute holds from source objects and fresh destination data, not cached flags."""
    decisions: dict[str, ca.Decision] = {}
    store = config.get("_corporate_store")
    notification_state_safe = store is not None
    try:
        proofs = ca.load_date_proofs(config.get("corporate_action_evidence_file"))
        if store is not None:
            store["inputs"] += [Path(proof["document"]) for proof in proofs.values()]
            ca.check_store(store)
    except (RuntimeError, OSError, ValueError):
        proofs = {}
        notification_state_safe = False
        log.error("Official corporate-action date evidence unavailable; affected events stay held")
    pairs = list(zip(config["account_ids"], config["query_ids"], strict=True))
    names = config.get("account_names") or config["account_ids"]
    targets = config.get("_source_accounts", {})
    prepared: dict[tuple[str, str], list[ca.Inventory]] = {}
    unavailable: set[tuple[str, str]] = set()
    # Complete evidence acquisition for every owner before the first decision.
    for pair in pairs:
        source, query = pair
        xml = config.get("_source_reports", {}).get(pair)
        if xml is None or targets.get(pair) is None:
            unavailable.add(pair)
            continue
        try:
            current = ca.parse_report(store, xml, source)
            prepared[pair] = (ca.retain_report(store, xml, source, query, mapping,
                                               dates={key: proof["effective_date"] for key, proof in proofs.items()})
                              if store is not None else [current])
            if current["account_held"] or not current["section_present"]:
                unavailable.add(pair)
        except (RuntimeError, OSError, ValueError, ParseError):
            unavailable.add(pair)
    groups = [{pair} for pair in pairs]
    possible_targets = {
        pair: ({targets[pair]} if targets.get(pair) is not None else
               {targets[other] for other_index, other in enumerate(pairs)
                if names[other_index] == names[index] and targets.get(other) is not None})
        for index, pair in enumerate(pairs)
    }
    for index, pair in enumerate(pairs):
        for other_index, other in enumerate(pairs[:index]):
            if (names[index] == names[other_index]
                    or possible_targets[pair] & possible_targets[other]):
                merged = set().union(*(group for group in groups if pair in group or other in group))
                groups = [group for group in groups if pair not in group and other not in group] + [merged]
    shared_holds = set().union(*(group for group in groups if len(group) > 1 and any(
        owner in unavailable or any(report["events"] for report in prepared.get(owner, []))
        for owner in group)))
    for source, query in pairs:
        pair = source, query
        target = targets.get(pair)
        fallback: ca.Decision = {"account_held": True, "symbols": set(), "effective": {},
                                 "findings": {}, "dates": {}, "normalized": set()}
        reports = prepared.get(pair)
        if reports is None or target is None:
            decisions[source] = fallback
            continue
        try:
            evidence: dict[str, dict[str, Any]] = {}
            symbols = {symbol for report in reports for event in report["events"].values()
                       if not set(event["reasons"]) - {"before_quantity_unproven", "effective_date_unproven"}
                       for row in event["rows"]
                       if (symbol := resolve_symbol(row.get("isin"), row.get("symbol"), mapping))}
            for symbol in sorted(symbols):
                try:
                    evidence[symbol] = ghost_corporate_evidence(config, symbol)
                except (RuntimeError, requests.RequestException):
                    log.warning("Corporate-action destination evidence unavailable for %s", symbol)
            decision = ca.decide(reports, source, target, mapping, snapshot, evidence, proofs)
            stale = {symbol for event in decision["findings"].values()
                     if "destination_holding_mismatch" in event["reasons"]
                     for symbol in event["symbols"] if symbol in evidence}
            for symbol in sorted(stale):
                log.info("Corporate-action holding mismatch: one fresh read-only observation for %s", symbol)
                try:
                    evidence[symbol] = ghost_corporate_evidence(config, symbol)
                except (RuntimeError, requests.RequestException):
                    evidence.pop(symbol, None)
            if stale:
                decision = ca.decide(reports, source, target, mapping, snapshot, evidence, proofs)
            if pair in shared_holds:
                decision["account_held"] = True
                log.warning("Corporate-action shared destination has unavailable or event-bearing owner evidence")
            if store is None:
                decision["account_held"] = True
            else:
                ca.publish_findings(store, source, decision, proofs)
            for key, event in decision["findings"].items():
                log.warning("Corporate action %s: held=%s reasons=%s conclusions=%s", key,
                            event["held"], ",".join(event["reasons"]), event["conclusions"])
            for symbol, quantity in decision["effective"].items():
                if symbol not in decision["symbols"] and not decision["account_held"]:
                    positions["qty"][(target, symbol)] = float(quantity)
            previous = decisions.get(source)
            if previous is not None:
                decision["account_held"] = decision["account_held"] or previous["account_held"]
                decision["symbols"].update(previous["symbols"])
            decisions[source] = decision
        except (RuntimeError, OSError, ValueError, ParseError):
            log.error("Corporate-action source/state evidence unavailable; account BUY/SELL held")
            decisions[source] = fallback
    config["_corporate_decisions"] = decisions
    outcome = config.get("_corporate_outcome")
    if outcome is not None:
        if store is not None and store["maintenance_warning"]:
            outcome["corporate_maintenance"] = True
        ca.prepare_notifications(outcome, config.get("corporate_action_state_file")
                                 if notification_state_safe else None, decisions)
