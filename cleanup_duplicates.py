#!/usr/bin/env python3
"""
Cleanup duplicate activities created by switching the IBKR Flex Query
from "Last Month" to "Last 365 Calendar Days".

Strategy (Option C):
  For each IBKR#-synced entry that has a matching manual entry
  (same symbol + type + qty + unitPrice + date within DATE_TOLERANCE days):
    1. PATCH the manual entry's comment to "IBKR#{tradeID}"
    2. DELETE the IBKR# entry

  IBKR# entries with no manual match are left as-is (genuinely new data).

Usage:
  python cleanup_duplicates.py           # dry-run (safe, prints what would happen)
  python cleanup_duplicates.py --apply   # apply changes
"""

import argparse
import json
import logging
from math import isfinite
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

DATE_TOLERANCE = timedelta(days=2)


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
    """Verify that PUT and DELETE on /api/v1/activities/{id} are reachable.

    Uses a GET (read-only) probe — never mutates anything.
    Raises RuntimeError if the endpoint is not accessible.
    """
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


def put_comment(config, activity, new_comment, dry_run):
    """PUT the full activity with an updated comment field."""
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
    """DELETE an activity."""
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
    """Conservatively exclude drafts/exclusions, including account tags."""
    account = activity.get("account") or {}
    tags = activity.get("tags", []) + account.get("tags", [])
    return (activity.get("isDraft") is True or activity.get("isExcluded") is True
            or account.get("isExcluded") is True
            or any(tag.get("id") in ("0c077abd-eca2-4cbb-818c-6cefbf2d169a",
                                     "f2e868af-8333-459f-b161-cbc6544c24bd")
                   for tag in tags))


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
              "tags", "account", "isDraft", "isExcluded")
    return (identity_of(fresh) == identity_of(planned)
            and all(fresh.get(field) == planned.get(field) for field in fields))


def main():
    parser = argparse.ArgumentParser(description="Clean up duplicate Ghostfolio activities")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry-run)")
    args = parser.parse_args()
    dry_run = not args.apply

    if dry_run:
        log.info("=== DRY-RUN mode — no changes will be made ===")
    else:
        log.info("=== APPLY mode — changes WILL be made ===")

    config = load_config()

    # Verify endpoints are reachable before doing anything (read-only probe)
    verify_endpoints(config)

    log.info("Fetching all activities from Ghostfolio...")

    # Safety log — written before any mutation
    log_file = Path(f"cleanup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json")
    all_activities = fetch_all_activities(config)
    log.info("Total activities: %d", len(all_activities))
    # Reject incomplete profile context before planning any destructive cleanup.
    for activity in all_activities:
        if activity.get("type") in ("BUY", "SELL"):
            validate_financial_evidence(activity)

    eligible_ids = [a["id"] for a in all_activities
                    if a.get("type") in ("BUY", "SELL")]
    if len(eligible_ids) != len(set(eligible_ids)):
        raise RuntimeError("Repeated cleanup activity id; refusing ambiguous list")

    # Split IBKR-synced vs manual
    ibkr = []
    manual = []
    for a in all_activities:
        if a.get("type") not in ("BUY", "SELL"):
            continue
        if inactive(a):
            continue
        comment = a.get("comment") or ""
        if comment.startswith("IBKR#"):
            ibkr.append(a)
        else:
            manual.append(a)

    log.info("IBKR# entries: %d", len(ibkr))
    log.info("Manual entries (no IBKR#): %d", len(manual))

    # Require a unique one-to-one assignment; never guess between real trades.
    matched_pairs = []
    unmatched_ibkr = []
    candidates = []
    for ib in ibkr:
        matches = []
        for m in manual:
            if identity_of(m) != identity_of(ib) or m["type"] != ib["type"]:
                continue
            if any(m[field] != ib[field]
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
    log.info("Matched pairs (will patch manual + delete IBKR#): %d", len(matched_pairs))
    log.info("Unmatched IBKR# entries (genuinely new, kept as-is): %d", len(unmatched_ibkr))

    if unmatched_ibkr:
        log.info("")
        log.info("Unmatched IBKR# entries (keeping):")
        for ib in unmatched_ibkr:
            log.info("  %s %s %s qty=%s price=%s date=%s",
                     ib["id"], symbol_of(ib), ib.get("type"),
                     ib.get("quantity"), ib.get("unitPrice"), ib.get("date"))

    log.info("")
    log.info("=== PAIRS TO PROCESS ===")
    for ib, m in matched_pairs:
        trade_id = (ib.get("comment") or "").split("#", 1)[1]
        new_comment = f"IBKR#{trade_id}"
        date_delta = abs(parse_date(ib.get("date")) - parse_date(m.get("date"))) if parse_date(ib.get("date")) and parse_date(m.get("date")) else "?"
        log.info("")
        log.info("  %s %s %sx@%s | date delta=%s",
                 symbol_of(ib), ib.get("type"), ib.get("quantity"), ib.get("unitPrice"), date_delta)
        log.info("  Manual  id=%s date=%s comment=%r", m["id"], m.get("date"), m.get("comment"))
        log.info("  IBKR#   id=%s date=%s comment=%r", ib["id"], ib.get("date"), ib.get("comment"))
        log.info("  Action: PATCH manual comment → %r | DELETE IBKR# entry", new_comment)

    if dry_run:
        log.info("")
        log.info("=== DRY-RUN complete. Run with --apply to execute. ===")
        return

    # Dump full snapshot of everything about to be touched before any mutation
    snapshot = [
        {
            "action": "PUT_comment_on_manual",
            "manual": m,
            "ibkr_to_delete": ib,
            "new_comment": f"IBKR#{(ib.get('comment') or '').split('#', 1)[1]}",
        }
        for ib, m in matched_pairs
    ]
    log_file.write_text(json.dumps(snapshot, indent=2, default=str))
    log.info("Safety log written to %s (%d pairs)", log_file, len(snapshot))

    # Apply
    log.info("")
    log.info("=== APPLYING CHANGES ===")
    patched = 0
    deleted = 0
    errors = 0

    for ib, m in matched_pairs:
        trade_id = (ib.get("comment") or "").split("#", 1)[1]
        new_comment = f"IBKR#{trade_id}"
        log.info("Processing %s %s %sx@%s...",
                 symbol_of(ib), ib.get("type"), ib.get("quantity"), ib.get("unitPrice"))

        m_full = fetch_fresh(config, m)
        ib_full = fetch_fresh(config, ib) if m_full is not None else None
        if m_full is None or ib_full is None:
            errors += 1
            continue

        # Replace both preimages with the verified fresh records before mutation.
        snapshot[matched_pairs.index((ib, m))]["manual"] = m_full
        snapshot[matched_pairs.index((ib, m))]["ibkr_to_delete"] = ib_full
        log_file.write_text(json.dumps(snapshot, indent=2, default=str))

        ok = put_comment(config, m_full, new_comment, dry_run=False)
        if ok:
            patched += 1
        else:
            errors += 1
            break

        ok = delete_activity(config, ib["id"], dry_run=False)
        if ok:
            deleted += 1
        else:
            errors += 1
            break

    log.info("")
    log.info("=== DONE ===")
    log.info("Patched: %d | Deleted: %d | Errors: %d", patched, deleted, errors)
    if errors:
        log.warning("Some operations failed — check logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
