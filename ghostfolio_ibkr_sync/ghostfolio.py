"""Ghostfolio API access: login exchange, reads, additive imports and cash updates.

Imports only ever add activities (never update or delete), and every financial
write is skipped when `dry_run` is set. The security token and the session bearer
travel only in a request body or Authorization header and are never logged; login
failures raise fixed messages for that reason.
"""

import json
import logging
import re
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, DecimalException
from math import isfinite
from typing import Any

import requests

from ghostfolio_ibkr_sync.config import validate_ghost_host
from ghostfolio_ibkr_sync.ibkr import _parse_float, log_lab_evidence

log = logging.getLogger(__name__)

# Run configuration as built by `config.load_config`; the import-uncertainty marker
# is added to it during a run.
Config = dict[str, Any]


def ghost_headers(token: str | None) -> dict[str, str]:
    """Return common headers for Ghostfolio API calls."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


GHOST_REDIRECT_ERROR = "Ghostfolio request redirected"


def ghost_response_is_redirect(resp: requests.Response) -> bool:
    """Return whether a Ghostfolio response is a redirect."""
    return 300 <= resp.status_code < 400


# (connect, read) inactivity timeouts for the login exchange
GHOST_AUTH_TIMEOUT = (10, 30)
# The bearer becomes an Authorization header value: printable ASCII, no space
_HEADER_SAFE_TOKEN_RE = re.compile(r"[\x21-\x7e]+")


def ghost_exchange_access_token(host: str, access_token: str) -> str:
    """Exchange the Ghostfolio security token for a session bearer.

    One POST /api/v1/auth/anonymous, no redirects (a redirect would carry the
    security token elsewhere) and no retry.  Every failure raises a fixed
    message: neither the request exception nor the response body is surfaced,
    as either could echo a credential.
    """
    validate_ghost_host(host)
    try:
        resp = requests.post(f"{host}/api/v1/auth/anonymous",
                             json={"accessToken": access_token},
                             timeout=GHOST_AUTH_TIMEOUT, allow_redirects=False)
    except requests.RequestException:
        raise RuntimeError("Ghostfolio login failed: network error") from None
    if not 200 <= resp.status_code < 300:
        raise RuntimeError(f"Ghostfolio login failed: HTTP {resp.status_code}")
    try:
        body = resp.json()
    except ValueError:
        raise RuntimeError("Ghostfolio login failed: response is not JSON") from None
    token = body.get("authToken") if isinstance(body, dict) else None
    if not isinstance(token, str) or not _HEADER_SAFE_TOKEN_RE.fullmatch(token):
        raise RuntimeError("Ghostfolio login failed: response has no usable authToken")
    return token


def activity_date_is_current(activity: Mapping[str, Any]) -> bool:
    """Conservatively refuse future instants (server drafts use local end of day)."""
    try:
        instant = datetime.fromisoformat(activity["date"].replace("Z", "+00:00"))
        return instant.tzinfo is not None and instant <= datetime.now(UTC)
    except (KeyError, TypeError, AttributeError, ValueError):
        return False


def activity_is_active(activity: Any) -> bool:
    """Follow Ghostfolio draft/exclusion tags; refuse malformed active context."""
    if not isinstance(activity, dict):
        raise RuntimeError("Invalid activity eligibility context")
    account = activity.get("account")
    if account is None:
        account = {}
    if not isinstance(account, dict):
        raise RuntimeError("Invalid account eligibility context")
    for context in (activity, account):
        for flag in ("isDraft", "isExcluded"):
            if flag in context and not isinstance(context[flag], bool):
                raise RuntimeError("Invalid activity eligibility flag")
        tags = context.get("tags", [])
        if (not isinstance(tags, list)
                or any(not isinstance(tag, dict) or not isinstance(tag.get("id"), str)
                       or not tag["id"].strip() for tag in tags)):
            raise RuntimeError("Invalid activity eligibility tags")
    inactive_tags = {"0c077abd-eca2-4cbb-818c-6cefbf2d169a",
                     "f2e868af-8333-459f-b161-cbc6544c24bd"}
    return not (activity.get("isDraft") or activity.get("isExcluded")
                or account.get("isDraft") or account.get("isExcluded")
                or any(tag["id"] in inactive_tags
                       for context in (activity, account) for tag in context.get("tags", [])))


def ghost_get_accounts(config: Config) -> Any:
    """Fetch all accounts from Ghostfolio."""
    url = f"{config['ghost_host']}/api/v1/account"
    resp = requests.get(url, headers=ghost_headers(config["ghost_token"]), timeout=30,
                        allow_redirects=False)
    if ghost_response_is_redirect(resp):
        raise RuntimeError(GHOST_REDIRECT_ERROR)
    resp.raise_for_status()
    return resp.json()


def ghost_find_account_id(config: Config, account_name: str) -> str | None:
    """Find a Ghostfolio account ID by name.

    Returns None if no account matches, so the caller can skip this account and
    still process the remaining ones.
    """
    data = ghost_get_accounts(config)
    accounts = data.get("accounts", data) if isinstance(data, dict) else data
    for acc in accounts:
        if acc.get("name") == account_name:
            if not activity_is_active({"account": acc}):
                raise RuntimeError("Ghostfolio target account is excluded; refusing sync")
            account_id: str = acc["id"]
            return account_id
    log.error("Ghostfolio account '%s' not found. Available: %s",
              account_name, [a["name"] for a in accounts])
    return None


def ghost_get_existing_orders(
    config: Config,
) -> tuple[set[str], set[tuple[str, str]], dict[str, Any]]:
    """Fetch all existing activities from Ghostfolio.

    Uses one GET /api/v1/activities (no paging).  The /api/v1/order
    endpoints were deprecated in Ghostfolio 2.248.0 and removed in 3.5.0.

    Prefers assetProfile; accepts legacy SymbolProfile only when the current
    key is absent. BUY, SELL and DIVIDEND require a nonempty string symbol.
    Raises RuntimeError on incomplete, redacted or invalid profile context,
    before reconciliation can import activities or update cash balances.

    Returns a tuple of (trade_ids, dividend_comments, positions):
    - trade_ids: set of tradeIDs extracted from "IBKR#..." comments
    - dividend_comments: set of (accountId, comment) tuples, e.g.
      ("acc-id", "dividend#SPY#2024-01-15"). Keyed by account so two accounts
      holding the same ISIN paid on the same day do not dedup against each other
    - positions: {"qty": net BUY-SELL qty by (accountId, symbol),
                  "isin_symbols": symbols seen by (accountId, isin),
                  "manual_sells": [[date, qty], ...] by (accountId, symbol) for
                                  SELLs without an IBKR# comment,
                  "manual_buys": same for BUYs without an IBKR# comment,
                  "dividend_dates": [(date, gross, currency, fee), ...] by
                                    (accountId, symbol) for every DIVIDEND without a
                                    connector comment; gross and fee are Decimal or None}
    """
    url = f"{config['ghost_host']}/api/v1/activities"
    headers = ghost_headers(config["ghost_token"])
    trade_ids = set()
    dividend_comments = set()
    positions: dict[str, Any] = {"qty": defaultdict(float), "isin_symbols": defaultdict(set),
                 "manual_sells": defaultdict(list), "manual_buys": defaultdict(list),
                 "dividend_dates": defaultdict(list)}

    # One request without skip/take: Ghostfolio has no take cap (default
    # MAX_SAFE_INTEGER), so one call returns one consistent list, with no
    # offset drift if activities are added or deleted between pages.
    # count comes from a separate query, so a mismatch fails closed.
    resp = requests.get(url, headers=headers, timeout=60, allow_redirects=False)
    if ghost_response_is_redirect(resp):
        raise RuntimeError(GHOST_REDIRECT_ERROR)
    resp.raise_for_status()
    # Keep the original JSON numbers before the normal float-based reader runs.
    # A mock/adapter without wire bytes cannot establish exact numeric evidence.
    exact_data = None
    if config.get("dry_run"):
        wire = getattr(resp, "content", None)
        if isinstance(wire, (str, bytes)) and wire:
            try:
                exact_data = json.loads(wire, parse_float=Decimal, parse_int=Decimal)
            except (ValueError, UnicodeError, DecimalException):
                pass  # The existing decoder below owns technical failures.
    data = resp.json()
    activities = data.get("activities", [])
    total = data.get("count")
    if total != len(activities):
        raise RuntimeError(
            f"Ghostfolio returned {len(activities)} activities but reports count={total}; "
            "refusing to sync on an incomplete list (duplicates risk)")
    # quantity is a required field; Ghostfolio returns it as null only when it
    # redacts the response (user restricted view, or a token without the
    # portfolioReadValues scope), which also nulls the IBKR# comments
    if any(a.get("quantity") is None for a in activities):
        raise RuntimeError(
            "Ghostfolio redacted activity values (quantity/comment are null): "
            "disable restricted view for the Ghostfolio user, or use a token "
            "with the portfolio:read:values scope; refusing to sync without "
            "existing IBKR# IDs (duplicates risk)")

    if config.get("dry_run"):
        exact_rows: Any = exact_data.get("activities") if isinstance(exact_data, dict) else None
        exact_available = isinstance(exact_rows, list) and len(exact_rows) == len(activities)
        positions["dividend_evidence"] = []

    for index, order in enumerate(activities):
        profile = {}
        if order.get("type") in ("BUY", "SELL", "DIVIDEND"):
            # Current API wins even if malformed: never hide an invalid current
            # profile behind a stale legacy value. Legacy-only responses remain
            # supported for Ghostfolio versions before 3.78.0.
            profile = (order["assetProfile"] if "assetProfile" in order
                       else order.get("SymbolProfile"))
            if (not isinstance(profile, dict)
                    or not isinstance(profile.get("symbol"), str)
                    or not profile["symbol"].strip()):
                raise RuntimeError(
                    f"Ghostfolio activity at index {index} has a missing or invalid "
                    "asset profile symbol (assetProfile / legacy SymbolProfile); "
                    "refusing to sync without position and reconciliation context")
        # comment is nullable in Ghostfolio, so JSON null arrives as None
        comment = order.get("comment") or ""
        if comment.startswith("IBKR#"):
            tid = comment.split("#", 1)[1]
            if tid:
                trade_ids.add(tid)
        elif comment.startswith("dividend#"):
            dividend_comments.add((order.get("accountId") or "", comment))

        active = activity_is_active(order)
        if config.get("dry_run") and order.get("type") == "DIVIDEND":
            raw = exact_rows[index] if exact_available else None
            exact = (isinstance(raw, dict)
                     and all(raw.get(key) == order.get(key)
                             for key in ("id", "type", "accountId", "comment", "date")))
            positions["dividend_evidence"].append({
                "activity": raw if exact else order, "exact_json": exact,
                "active": active, "index": index})
        if order.get("type") in ("BUY", "SELL", "DIVIDEND"):
            source = profile.get("dataSource")
            if not isinstance(source, str) or not source.strip():
                raise RuntimeError("Ghostfolio activity has missing data source; refusing sync")
            if not active or source != "YAHOO":
                continue

        if order.get("type") == "DIVIDEND":
            symbol = profile["symbol"]
            if symbol and not comment.startswith("dividend#"):
                positions["dividend_dates"][(order.get("accountId") or "", symbol)].append(
                    ((order.get("date") or "")[:10], *_existing_dividend_amounts(order, profile)))

        if order.get("type") in ("BUY", "SELL"):
            qty = _parse_float(order.get("quantity"))
            if qty is None or not isfinite(qty) or qty < 0:
                raise RuntimeError("Ghostfolio has invalid holding quantity; refusing sync")
            if order["type"] == "SELL":
                qty = -qty
            account_id = order.get("accountId") or ""
            symbol = profile["symbol"]
            if symbol:
                positions["qty"][(account_id, symbol)] += qty
                if profile.get("isin"):
                    positions["isin_symbols"][(account_id, profile["isin"])].add(symbol)
                if not comment.startswith("IBKR#"):
                    key = "manual_sells" if order["type"] == "SELL" else "manual_buys"
                    positions[key][(account_id, symbol)].append(
                        [(order.get("date") or "")[:10], abs(qty)])

    log.info("Scanned %d existing Ghostfolio activities", len(activities))
    return trade_ids, dividend_comments, positions


# Ghostfolio aborts the whole import on the first activity whose symbol the
# data provider cannot resolve, returning a 400 whose message names that symbol
# (data-provider.service.ts validateActivities, confirmed at 3.80.2). The symbol
# is quoted; the backslashes tolerate both the decoded message and the raw
# escaped JSON text.
_UNRESOLVED_SYMBOL_RE = re.compile(
    r'symbol \(\\?"([^"\\]+)\\?"\) cannot be resolved by the data source')


def parse_unresolved_symbol(body: Any, text: str = "") -> str | None:
    """Return the ticker Ghostfolio could not resolve from an import 400, else None.

    None means the 400 is not a per-symbol resolution error (too many
    activities, premium required, invalid data source, ...) and must not be
    retried.  body is the parsed JSON (dict or None); text is the raw fallback.
    """
    messages = []
    if isinstance(body, dict):
        msg = body.get("message")
        if isinstance(msg, list):
            messages = [str(x) for x in msg]
        elif msg:
            messages = [str(msg)]
    haystack = " ".join(messages) if messages else (text or "")
    match = _UNRESOLVED_SYMBOL_RE.search(haystack)
    return match.group(1) if match else None


def accepted_import_subset(
    submitted: list[dict[str, Any]], body: Any,
) -> list[dict[str, Any]]:
    """Map server-created rows to unique submitted identities, never sent counts."""
    if not isinstance(body, dict) or not isinstance(body.get("activities"), list):
        raise RuntimeError("Import response has no accepted activity list")
    by_key = {}
    for activity in submitted:
        key = (activity.get("accountId"), activity.get("comment"))
        if any(not isinstance(v, str) or not v for v in key) or key in by_key:
            raise RuntimeError("Ambiguous submitted import identity")
        by_key[key] = activity
    accepted = []
    seen = set()
    created_ids = set()
    for row in body["activities"]:
        if not isinstance(row, dict) or row.get("error"):
            raise RuntimeError("Invalid accepted import activity")
        key = (row.get("accountId"), row.get("comment"))
        if any(not isinstance(v, str) or not v for v in key) or key not in by_key or key in seen:
            raise RuntimeError("Unmatched or repeated accepted import identity")
        original = by_key[key]
        if not activity_is_active(row) or not activity_date_is_current(row):
            raise RuntimeError("Created activity is inactive; cannot update active holdings")
        # Preserve listing compatibility: current key wins, even if invalid.
        profile = (row["assetProfile"] if "assetProfile" in row
                   else row.get("SymbolProfile"))
        if (not isinstance(row.get("id"), str) or not row["id"].strip()
                or row["id"] in created_ids
                or not isinstance(profile, dict)
                or not isinstance(profile.get("symbol"), str) or not profile["symbol"].strip()
                or profile.get("dataSource") != original.get("dataSource")):
            raise RuntimeError("Accepted activity lacks created identity or matching data source")
        try:
            returned_date = datetime.fromisoformat(row["date"].replace("Z", "+00:00"))
            submitted_date = datetime.fromisoformat(original["date"].replace("Z", "+00:00"))
        except (KeyError, AttributeError, TypeError, ValueError):
            raise RuntimeError("Accepted activity lacks a valid date") from None
        if (returned_date.tzinfo is None or submitted_date.tzinfo is None
                or returned_date != submitted_date):
            raise RuntimeError("Accepted activity has a different date")
        for field in ("quantity", "unitPrice", "fee"):
            for value in (row.get(field), original.get(field)):
                if (isinstance(value, bool) or not isinstance(value, (int, float))
                        or not isfinite(value) or value < 0):
                    raise RuntimeError("Accepted activity has invalid financial evidence")
        for field in ("type", "quantity", "unitPrice", "fee", "currency"):
            if row.get(field) != original.get(field):
                raise RuntimeError("Accepted activity differs from submitted financial evidence")
        seen.add(key)
        created_ids.add(row["id"])
        accepted.append({**original, "symbol": profile["symbol"]})
    return accepted


def mark_import_uncertain(config: Config, activities: list[dict[str, Any]]) -> None:
    """A POST may have written records; block later queries to these accounts."""
    config.setdefault("_uncertain_import_accounts", set()).update(
        a["accountId"] for a in activities if a.get("accountId"))


def ghost_import_activities(
    config: Config, activities: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """Import activities into Ghostfolio.  Returns (imported, ok).

    imported — the activities Ghostfolio accepted, for the caller's dedup
               bookkeeping; only rows identified in the server response.
               Dry-run returns the proposed rows for simulation only.
    ok       — True for a clean run, False when the run is degraded (a symbol
               was dropped) or failed, so the caller exits non-zero.

    Ghostfolio validates the whole /api/v1/import batch and aborts on the first
    activity whose symbol the data provider cannot resolve, failing trades and
    dividends alike with a single 400.  To stop one bad ticker from costing the
    whole account, such a 400 drops that symbol's activities, warns, and retries
    the reduced batch; the run still ends non-zero so the skipped symbol stays
    visible.  Other 400s (too many activities, premium, ...) are not per-symbol
    and fail hard without retrying.

    Ghostfolio reports its own duplicate detection per activity in a 2xx and
    silently skips those, so a short accepted count is not a failure.
    """
    if config.get("dry_run"):
        log_lab_evidence("preview", activities)
    if not activities:
        log.info("No new activities to import")
        return [], True
    if config.get("dry_run"):
        log.info("[DRY RUN] would import %d activities (no POST sent):", len(activities))
        for a in activities:
            log.info("[DRY RUN]   %-8s %-14s qty=%s price=%s %s fee=%s  %s",
                     a.get("type"), a.get("symbol"), a.get("quantity"),
                     a.get("unitPrice"), a.get("currency"), a.get("fee"),
                     a.get("comment"))
        return list(activities), True
    url = f"{config['ghost_host']}/api/v1/import"
    remaining = list(activities)
    dropped_symbols: list[str] = []
    # Each iteration drops one symbol, so the loop can never run more times than
    # there are distinct symbols (+1 for the final accepting POST).
    max_attempts = len({a.get("symbol") for a in activities}) + 1

    for _ in range(max_attempts):
        try:
            resp = requests.post(url, headers=ghost_headers(config["ghost_token"]),
                                 json={"activities": remaining}, timeout=60,
                                 allow_redirects=False)
        except requests.RequestException as exc:
            log.error("Import request failed: %s", exc)
            mark_import_uncertain(config, remaining)
            return [], False

        if ghost_response_is_redirect(resp):
            mark_import_uncertain(config, remaining)
            log.error(GHOST_REDIRECT_ERROR)
            return [], False

        try:
            body = resp.json()
        except ValueError:
            body = None

        if 200 <= resp.status_code < 300:
            try:
                imported = accepted_import_subset(remaining, body)
            except RuntimeError as exc:
                log.error("Cannot establish accepted import outcome: %s; inspect Ghostfolio before retry", exc)
                mark_import_uncertain(config, remaining)
                return [], False
            log.info("Ghostfolio created %d of %d submitted activities", len(imported), len(remaining))
            if dropped_symbols:
                log.warning("Imported without %d unresolved symbol(s): %s — add a mapping entry "
                            "(symbol_mapping) so they are recognised next run",
                            len(dropped_symbols), ", ".join(dropped_symbols))
            return imported, not dropped_symbols

        symbol = parse_unresolved_symbol(body, resp.text)
        if symbol is None:
            mark_import_uncertain(config, remaining)
            log.error("Import failed (%d): %s", resp.status_code, resp.text)
            log.error("Check your mapping file - a symbol may not be recognised by Ghostfolio")
            return [], False

        before = len(remaining)
        remaining = [a for a in remaining if a.get("symbol") != symbol]
        if before == len(remaining):
            # The named symbol matches no activity we can drop (e.g. a
            # server-side resolved name); retrying would loop forever.
            log.error("Ghostfolio rejected symbol %r but no matching activity was found to drop; "
                      "aborting import for this account. Response: %s", symbol, resp.text)
            return [], False
        dropped_symbols.append(symbol)
        log.warning("Ghostfolio cannot resolve symbol %r (%d activity/ies dropped); retrying without it",
                    symbol, before - len(remaining))
        if not remaining:
            log.warning("All activities were dropped as unresolved; nothing imported for this account")
            return [], False

    log.error("Import did not converge after dropping %d symbol(s): %s",
              len(dropped_symbols), ", ".join(dropped_symbols))
    return [], False


def ghost_update_cash_balance(
    config: Config, account_id: str, balance: float, base_currency: str | None,
) -> bool:
    """Update the cash balance on a Ghostfolio account.  Returns True on success.

    The GET response carries far more than the update DTO accepts (aggregations,
    relations, timestamps).  Ghostfolio 3.x validates bodies with
    forbidNonWhitelisted, so echoing it back is a hard 400.  The payload is
    therefore built explicitly from the five fields UpdateAccountDto requires:
    balance, currency, id, name and platformId (nullable).

    comment, tags and isExcluded are optional in the DTO and deliberately left
    out - Prisma does not touch a column that is absent from the update, so
    omitting them preserves the stored values.  For isExcluded that also keeps
    the payload portable: it was a deprecated DTO field up to Ghostfolio 3.38.0
    and removed in 3.39.0, so sending it fails outright on newer instances.

    The balance is the IBKR base-currency figure with no conversion, so the
    Ghostfolio account must have the same currency: a mismatch, or a report
    without a base currency, sends no PUT and returns False.  A dry run still
    does the read-only GET and the check, so the preview matches a live run.
    """
    if not base_currency:
        log.error("Cash balance not updated for account %s: the report has no base currency "
                  "(Account Information CurrencyPrimary missing from the Flex Query)", account_id)
        return False
    url = f"{config['ghost_host']}/api/v1/account/{account_id}"
    resp = requests.get(url, headers=ghost_headers(config["ghost_token"]), timeout=30,
                        allow_redirects=False)
    if ghost_response_is_redirect(resp):
        raise RuntimeError(GHOST_REDIRECT_ERROR)
    resp.raise_for_status()
    account_data = resp.json()

    if account_data["currency"] != base_currency:
        log.error("Cash balance not updated for account %s: IBKR base currency %s differs "
                  "from Ghostfolio account currency %s", account_id, base_currency,
                  account_data["currency"])
        return False
    log_lab_evidence("cash", {"accountId": account_id, "balance": balance, "currency": base_currency})
    if config.get("dry_run"):
        log.info("[DRY RUN] would set cash balance for account %s to %.2f (no PUT sent)",
                 account_id, balance)
        return True

    payload = {
        "balance": balance,
        "currency": account_data["currency"],
        "id": account_id,
        "name": account_data["name"],
        "platformId": account_data.get("platformId") or config.get("ghost_platform_id") or None,
    }
    resp = requests.put(url, headers=ghost_headers(config["ghost_token"]),
                        json=payload, timeout=30, allow_redirects=False)
    if ghost_response_is_redirect(resp):
        log.error(GHOST_REDIRECT_ERROR)
        return False
    if resp.status_code >= 400:
        log.error("Failed to update cash balance (%d): %s", resp.status_code, resp.text)
        return False
    log.info("Updated cash balance for account %s to %.2f", account_id, balance)
    return True


def _existing_dividend_amounts(
    order: Mapping[str, Any], profile: Mapping[str, Any],
) -> tuple[Decimal | None, str | None, Decimal | None]:
    """Return (gross, currency, fee) of an existing Ghostfolio dividend.

    gross = quantity * unitPrice and fee are Decimal, None when missing or invalid.
    A null activity currency falls back to the profile currency.
    """
    def decimal(value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            result = Decimal(str(value))
        except (DecimalException, ValueError):
            return None
        return result if result.is_finite() else None

    quantity, price, fee = (decimal(order.get(key)) for key in ("quantity", "unitPrice", "fee"))
    gross = quantity * price if quantity is not None and price is not None else None
    currency = order.get("currency")
    if currency is None:
        currency = profile.get("currency")
    return gross, currency if isinstance(currency, str) and currency else None, fee
