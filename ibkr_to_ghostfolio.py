#!/usr/bin/env python3
"""Sync Interactive Brokers trades and dividends to a self-hosted Ghostfolio instance."""

import json  # noqa: F401
import logging
import os
import subprocess  # noqa: F401
import sys

import requests  # noqa: F401

# Transitional until the image installs the package: the notification worker
# runs this file with -I, which leaves the script directory off sys.path.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)

from ghostfolio_ibkr_sync import notify  # noqa: E402
from ghostfolio_ibkr_sync.app import (  # noqa: E402,F401
    finalize_run,
    legacy_token_expiry_days,
    main,
    process_account,
    run_sync,
)
from ghostfolio_ibkr_sync.config import (  # noqa: E402,F401
    APPRISE_URLS_MAX,
    NOTIFY_PAYLOAD_MAX,
    dry_run_requested,
    load_config,
    load_notification_config,
    timezone_preview_reason,
)
from ghostfolio_ibkr_sync.diagnostics import (  # noqa: E402,F401
    _historical_currency_context,
    _historical_currency_reason,
    _historical_destination,
    _historical_destination_currency,
    _historical_identity_checks,
    _historical_proximity,
    _historical_representations,
    _historical_source_values,
    _historical_values,
    READABLE_ACTIONS,
    MATCH_REASONS,
    _declared_rate_rounding,
    _finding_action,
    _format_match,
    _match_action,
    _match_candidates,
    _match_is_strong,
    _plain,
    _plain_counts,
    _plain_deltas,
    _plain_money,
    _plain_signed,
    _plain_signed_money,
    _plain_values,
    _propose_match,
    _readable_action,
    _readable_set,
    _readable_values,
    classify_dividend_findings,
    format_historical_dividend_finding,
    historical_dividend_comparison,
    log_historical_dividend_comparison,
    classify_dividend_deltas,
    dividend_declared_rate,
    historical_dividend_findings,
)
from ghostfolio_ibkr_sync.ghostfolio import (  # noqa: E402,F401
    GHOST_AUTH_TIMEOUT,
    GHOST_REDIRECT_ERROR,
    _existing_dividend_amounts,
    _HEADER_SAFE_TOKEN_RE,
    _UNRESOLVED_SYMBOL_RE,
    accepted_import_subset,
    activity_date_is_current,
    activity_is_active,
    ghost_exchange_access_token,
    ghost_find_account_id,
    ghost_get_accounts,
    ghost_get_existing_orders,
    ghost_headers,
    ghost_import_activities,
    ghost_response_is_redirect,
    ghost_update_cash_balance,
    mark_import_uncertain,
    parse_unresolved_symbol,
)
from ghostfolio_ibkr_sync.ibkr import (  # noqa: E402,F401
    DIVIDEND_ACCRUAL_REQUIRED,
    DIVIDEND_CASH_TYPES,
    DIVIDEND_FIELD_NAMES,
    DIVIDEND_PAYMENT_KEYS,
    FLEX_SUFFIX_PATTERN,
    IBKR_ALLOWED_STMT_PREFIXES,
    IBKR_MAX_XML_BYTES,
    IBKR_NETWORK_RETRY_DELAYS,
    IBKR_SEND_RETRY_CODES,
    IBKR_SEND_RETRY_DELAYS,
    IBKR_SEND_URL,
    IBKR_STMT_URL,
    SKIP_ASSET_CATEGORIES,
    WITHHOLDING_CASH_TYPE,
    _dividend_cash_sum,
    _dividend_decimal,
    _ibkr_get,
    _parse_float,
    _redact,
    dividend_field_prerequisites,
    dividend_input_compatible,
    fetch_flex_report,
    flex_provenance_failures,
    historical_dividend_report_window,
    log_lab_evidence,
    parse_base_currency,
    parse_cash_dividends,
    parse_cash_report,
    parse_ibkr_datetime,
    parse_trades,
)
from ghostfolio_ibkr_sync.notify import (  # noqa: E402,F401
    FORCED_PREVIEW_NOTIFY_TITLE,
    NOTIFY_ENV_ALLOWLIST,
    NOTIFY_EXIT_STATUS,
    NOTIFY_TITLE,
    NOTIFY_WORKER_FLAG,
    TOKEN_EXPIRY_NOTIFY_TITLE,
    _notify_worker_argv,
    _stop_worker,
    build_failure_summary,
    build_forced_preview_summary,
    build_token_expiry_summary,
    notify_worker,
    send_notification,
)
from ghostfolio_ibkr_sync.outcome import (  # noqa: E402,F401
    MAX_OUTCOME_FAILURES,
    OUTCOME_REASONS,
    is_token_rejection,
    new_run_outcome,
    record_failure,
)
from ghostfolio_ibkr_sync.sync import (  # noqa: E402,F401
    CURRENCY_MINOR_UNITS,
    DIVIDEND_MATCH_DAYS,
    MINOR_UNIT_MARKETS,
    _dividend_date_matches,
    _dividend_day,
    _historical_currency,
    _historical_minor_unit,
    _match_manual_entry,
    _proximity_amounts,
    _source_dividend_fee,
    convert_dividend_to_activity,
    convert_trade_to_activity,
    dividend_dedup_decision,
    dividend_structured_quantity,
    filter_trades_by_holdings,
    load_mapping,
    log_dividend_proximity_skip,
    minor_unit_conversion,
    rejected_sell_symbols,
    resolve_symbol,
    split_import_phases,
    trade_id_decision,
    unique_trades,
)

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)
# urllib3 logs full request lines (incl. the IBKR token query param) at DEBUG.
logging.getLogger("urllib3").setLevel(logging.WARNING)


# The notification worker re-runs this file until task 4.2 installs the package.
notify.WORKER_SCRIPT = __file__

if __name__ == "__main__":
    if sys.argv[1:] == [NOTIFY_WORKER_FLAG]:
        sys.exit(notify_worker())
    sys.exit(main())
