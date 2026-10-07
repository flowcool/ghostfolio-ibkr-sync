#!/usr/bin/env python3
"""
Cleanup duplicate dividend activities created by the 365-day Flex Query re-import.

The sync script creates entries with comment "dividend#{symbol}#{date}".
Manual entries have no comment or a non-dividend# comment.

Strategy:
  For each dividend# entry that matches a manual DIVIDEND entry
  (same symbol + qty + unitPrice + date within DATE_TOLERANCE):
    1. PUT the manual entry's comment to "dividend#{symbol}#{date}"
    2. DELETE the dividend# entry

  dividend# entries with no manual match are left as-is (genuinely new data).

Usage:
  python cleanup_dividends.py           # dry-run (safe, prints what would happen)
  python cleanup_dividends.py --apply   # apply changes

Each apply creates a private YAML recovery journal with exact preimages and outcomes.
Use --resume JOURNAL to inspect, then --resume JOURNAL --apply for bounded recovery.
PUT and DELETE remain nontransactional; quiesce concurrent writers.
"""

import argparse
import logging
from math import isfinite
import os
import sys
from datetime import datetime, timezone, timedelta

import requests

from ibkr_to_ghostfolio import activity_is_active
from cleanup_recovery import process_pairs, resume_cleanup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# IBKR pay date vs ex-date (manually entered) can differ by weeks.
# Quarterly dividends are ~90 days apart, so ±35 days avoids false positives
# between consecutive payments while covering the ex-date/pay-date gap.
DATE_TOLERANCE = timedelta(days=35)
DATE_WARN_THRESHOLD = timedelta(days=7)  # log warning if delta exceeds this


def load_config():
    required = ["GHOST_TOKEN", "GHOST_HOST"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}")
    return {
        "ghost_token": os.environ["GHOST_TOKEN"],
        "ghost_host": os.environ["GHOST_HOST"].rstrip("/"),
    }


def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def fetch_all_activities(config):
    url = f"{config['ghost_host']}/api/v1/activities"
    resp = requests.get(url, headers=headers(config["ghost_token"]), timeout=60)
    resp.raise_for_status()
    data = resp.json()
    activities = data.get("activities")
    if not isinstance(activities, list) or data.get("count") != len(activities):
        raise RuntimeError("Incomplete activity list; refusing cleanup")
    return activities


def parse_date(iso):
    """Require a valid instant; interpret legacy naive dates as UTC."""
    if not isinstance(iso, str) or not iso.strip():
        return None
    try:
        parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def verify_endpoints(config):
    """Read-only probe — never mutates anything."""
    url = f"{config['ghost_host']}/api/v1/activities"
    resp = requests.get(url, headers=headers(config["ghost_token"]), timeout=30)
    resp.raise_for_status()
    acts = resp.json().get("activities", [])
    if not acts:
        raise RuntimeError("No activities found — cannot verify endpoint")
    probe_id = acts[0]["id"]
    probe_url = f"{config['ghost_host']}/api/v1/activities/{probe_id}"
    probe = requests.get(probe_url, headers=headers(config["ghost_token"]), timeout=10)
    if probe.status_code != 200:
        raise RuntimeError(
            f"GET /api/v1/activities/{{id}} returned {probe.status_code} — "
            "endpoint not available on this Ghostfolio version"
        )
    log.info("Endpoint verified: GET /api/v1/activities/{id} → 200 (probe: %s)", probe_id)


def profile_of(activity):
    """Prefer the current profile and refuse unsafe legacy fallback."""
    if not isinstance(activity, dict):
        raise RuntimeError("Missing or invalid activity object; refusing cleanup")
    profile = (activity["assetProfile"] if "assetProfile" in activity
               else activity.get("SymbolProfile"))
    if (not isinstance(profile, dict)
            or not isinstance(profile.get("symbol"), str)
            or not profile["symbol"].strip()):
        raise RuntimeError("Missing or invalid asset profile symbol; refusing cleanup")
    return profile


def symbol_of(activity):
    return profile_of(activity)["symbol"]


def identity_of(activity):
    """Require complete account, currency and asset identity for cleanup."""
    profile = profile_of(activity)
    identity = (activity.get("accountId"), activity.get("currency"),
                profile.get("dataSource"), profile["symbol"])
    if any(not isinstance(value, str) or not value.strip() for value in identity):
        raise RuntimeError("Incomplete cleanup identity (account, currency or data source)")
    return identity


def validate_financial_evidence(activity):
    """Reject incomplete or nonfinite evidence before planning any writes."""
    identity_of(activity)
    if not isinstance(activity.get("id"), str) or not activity["id"].strip():
        raise RuntimeError("Missing cleanup activity id")
    if parse_date(activity.get("date")) is None:
        raise RuntimeError("Invalid cleanup activity date")
    for field in ("quantity", "unitPrice", "fee"):
        value = activity.get(field)
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not isfinite(value) or value < 0
                or (field == "quantity" and value == 0)):
            raise RuntimeError(f"Invalid cleanup financial evidence: {field}")
    comment = activity.get("comment")
    if comment is not None and not isinstance(comment, str):
        raise RuntimeError("Invalid cleanup comment")


def inactive(activity):
    return not activity_is_active(activity)


def fetch_fresh(config, planned):
    url = f"{config['ghost_host']}/api/v1/activities/{planned['id']}"
    try:
        response = requests.get(url, headers=headers(config["ghost_token"]), timeout=10)
        if not 200 <= response.status_code < 300:
            raise RuntimeError("unreadable activity")
        fresh = response.json()
        validate_financial_evidence(fresh)
        if inactive(fresh) or not snapshot_matches(fresh, planned):
            raise RuntimeError("changed or inactive activity")
        return fresh
    except (requests.RequestException, ValueError, RuntimeError, TypeError, AttributeError):
        log.error("  Cannot verify unchanged activity %s; refusing pair", planned["id"])
        return None


def snapshot_matches(fresh, planned):
    """Refuse a stale plan before tagging the manual entry or deleting its pair."""
    fields = ("id", "type", "date", "quantity", "unitPrice", "fee", "comment",
              "tags", "account", "isDraft", "isExcluded", "userId")
    return (identity_of(fresh) == identity_of(planned)
            and all(fresh.get(field) == planned.get(field) for field in fields))


def put_comment(config, activity, new_comment, dry_run):
    profile = profile_of(activity)
    identity_of(activity)
    source = profile["dataSource"]
    activity_id = activity["id"]
    url = f"{config['ghost_host']}/api/v1/activities/{activity_id}"
    if dry_run:
        log.info("  [DRY-RUN] PUT %s → comment=%r", activity_id, new_comment)
        return True
    payload = {
        "id": activity_id,
        "accountId": activity["accountId"],
        "comment": new_comment,
        "currency": activity["currency"],
        "date": activity["date"],
        "fee": activity["fee"],
        "quantity": activity["quantity"],
        "symbol": profile["symbol"],
        "type": activity["type"],
        "unitPrice": activity["unitPrice"],
        "dataSource": source,
    }
    try:
        resp = requests.put(url, headers=headers(config["ghost_token"]), json=payload, timeout=30)
    except requests.RequestException:
        log.error("  PUT outcome uncertain; inspect safety log before recovery")
        return False
    if not 200 <= resp.status_code < 300:
        log.error("  PUT failed (%d): %s", resp.status_code, resp.text[:200])
        return False
    log.info("  PUT OK: %s comment → %r", activity_id, new_comment)
    return True


def delete_activity(config, activity_id, dry_run):
    url = f"{config['ghost_host']}/api/v1/activities/{activity_id}"
    if dry_run:
        log.info("  [DRY-RUN] DELETE %s", activity_id)
        return True
    try:
        resp = requests.delete(url, headers=headers(config["ghost_token"]), timeout=30)
    except requests.RequestException:
        log.error("  DELETE outcome uncertain; inspect safety log before recovery")
        return False
    if not 200 <= resp.status_code < 300:
        log.error("  DELETE failed (%d): %s", resp.status_code, resp.text[:200])
        return False
    log.info("  DELETE OK: %s", activity_id)
    return True


def main():
    parser = argparse.ArgumentParser(description="Clean up duplicate dividend activities")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry-run)")
    parser.add_argument("--journal", help="New private YAML journal path for --apply")
    parser.add_argument("--resume", help="Inspect existing YAML journal; add --apply to resume")
    args = parser.parse_args()
    if args.resume and args.journal:
        parser.error("--journal cannot be combined with --resume")
    if args.journal and not args.apply:
        parser.error("--journal requires --apply")
    if args.resume:
        try:
            resume_cleanup(sys.modules[__name__], load_config(), args.resume, apply=args.apply)
        except (RuntimeError, OSError) as exc:
            log.error("Recovery stopped: %s", exc)
            sys.exit(1)
        return
    dry_run = not args.apply

    if dry_run:
        log.info("=== DRY-RUN mode — no changes will be made ===")
    else:
        log.info("=== APPLY mode — changes WILL be made ===")

    config = load_config()
    verify_endpoints(config)

    log.info("Fetching all activities from Ghostfolio...")
    all_activities = fetch_all_activities(config)
    log.info("Total activities: %d", len(all_activities))
    # Reject incomplete profile context before planning any destructive cleanup.
    for activity in all_activities:
        if activity.get("type") in ("DIVIDEND",):
            validate_financial_evidence(activity)

    eligible_ids = [a["id"] for a in all_activities
                    if a.get("type") in ("DIVIDEND",)]
    if len(eligible_ids) != len(set(eligible_ids)):
        raise RuntimeError("Repeated cleanup activity id; refusing ambiguous list")

    # Split dividend# (IBKR-synced) vs manual dividends
    div_ibkr = []   # comment starts with "dividend#"
    div_manual = [] # type=DIVIDEND, comment does NOT start with "dividend#"
    for a in all_activities:
        if a.get("type") != "DIVIDEND":
            continue
        if inactive(a):
            continue
        comment = a.get("comment") or ""
        if comment.startswith("dividend#"):
            div_ibkr.append(a)
        else:
            div_manual.append(a)

    log.info("dividend# entries (IBKR-synced): %d", len(div_ibkr))
    log.info("Manual dividend entries: %d", len(div_manual))

    # Require a unique one-to-one assignment; never guess between real trades.
    matched_pairs = []
    unmatched_ibkr = []
    candidates = []
    for ib in div_ibkr:
        matches = []
        for m in div_manual:
            if identity_of(m) != identity_of(ib) or m["type"] != ib["type"]:
                continue
            if any(abs(m[field] - ib[field]) > 1e-9
                   for field in ("quantity", "unitPrice", "fee")):
                continue
            if abs(parse_date(ib["date"]) - parse_date(m["date"])) <= DATE_TOLERANCE:
                matches.append(m)
        candidates.append((ib, matches))
    for ib, matches in candidates:
        if (len(matches) == 1
                and sum(any(m["id"] == matches[0]["id"] for m in other)
                        for _, other in candidates) == 1):
            matched_pairs.append((ib, matches[0]))
        else:
            unmatched_ibkr.append(ib)
            if matches:
                log.warning("Ambiguous cleanup pair for %s; kept unchanged", ib["id"])

    log.info("")
    log.info("=== RESULTS ===")
    log.info("Matched pairs (will patch manual + delete dividend#): %d", len(matched_pairs))
    log.info("Unmatched dividend# entries (genuinely new, kept as-is): %d", len(unmatched_ibkr))

    if unmatched_ibkr:
        log.info("")
        log.info("Unmatched dividend# entries (keeping):")
        for ib in unmatched_ibkr:
            log.info("  %s qty=%s price=%s date=%s comment=%r",
                     symbol_of(ib), ib.get("quantity"), ib.get("unitPrice"),
                     ib.get("date"), ib.get("comment"))

    log.info("")
    log.info("=== PAIRS TO PROCESS ===")
    for ib, m in matched_pairs:
        new_comment = ib.get("comment")  # e.g. "dividend#AAPL#2026-03-15"
        ib_date = parse_date(ib.get("date"))
        m_date = parse_date(m.get("date"))
        date_delta = abs(ib_date - m_date) if ib_date and m_date else "?"
        log.info("")
        if isinstance(date_delta, timedelta) and date_delta > DATE_WARN_THRESHOLD:
            log.warning("  *** DATE DELTA %s > %s days — review this pair! ex-date vs pay-date?",
                        date_delta, DATE_WARN_THRESHOLD.days)
        log.info("  %s qty=%s price=%s | date delta=%s",
                 symbol_of(ib), ib.get("quantity"), ib.get("unitPrice"), date_delta)
        log.info("  Manual   id=%s date=%s comment=%r", m["id"], m.get("date"), m.get("comment"))
        log.info("  dividend# id=%s date=%s comment=%r", ib["id"], ib.get("date"), ib.get("comment"))
        log.info("  Action: PUT manual comment → %r | DELETE dividend# entry", new_comment)

    if dry_run:
        log.info("")
        log.info("=== DRY-RUN complete. Run with --apply to execute. ===")
        return

    try:
        process_pairs(sys.modules[__name__], config, matched_pairs, args.journal)
    except (RuntimeError, OSError) as exc:
        log.error("Cleanup stopped: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
