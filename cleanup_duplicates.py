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
    return resp.json().get("activities", [])


def parse_date(iso):
    """Parse ISO date string to UTC-aware datetime."""
    if not iso:
        return None
    iso = iso.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso)
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
        "symbol": (activity.get("SymbolProfile") or {}).get("symbol"),
        "type": activity["type"],
        "unitPrice": activity["unitPrice"],
        "dataSource": (activity.get("SymbolProfile") or {}).get("dataSource"),
    }
    resp = requests.put(url, headers=headers(config["ghost_token"]), json=payload, timeout=30)
    if resp.status_code >= 400:
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
    resp = requests.delete(url, headers=headers(config["ghost_token"]), timeout=30)
    if resp.status_code >= 400:
        log.error("  DELETE failed (%d): %s", resp.status_code, resp.text[:200])
        return False
    log.info("  DELETE OK: %s", activity_id)
    return True


def symbol_of(activity):
    return (activity.get("SymbolProfile") or {}).get("symbol", "")


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

    # Split IBKR-synced vs manual
    ibkr = []
    manual = []
    for a in all_activities:
        comment = a.get("comment") or ""
        if comment.startswith("IBKR#"):
            ibkr.append(a)
        else:
            manual.append(a)

    log.info("IBKR# entries: %d", len(ibkr))
    log.info("Manual entries (no IBKR#): %d", len(manual))

    # For each IBKR# entry, find a matching manual entry
    matched_pairs = []    # (ibkr_entry, manual_entry)
    unmatched_ibkr = []   # IBKR# entries with no manual counterpart (genuinely new)
    used_manual_ids = set()

    for ib in ibkr:
        ib_sym = symbol_of(ib)
        ib_type = ib.get("type")
        ib_qty = ib.get("quantity")
        ib_price = ib.get("unitPrice")
        ib_date = parse_date(ib.get("date"))

        best = None
        best_delta = None

        for m in manual:
            if m["id"] in used_manual_ids:
                continue
            if symbol_of(m) != ib_sym:
                continue
            if m.get("type") != ib_type:
                continue
            if m.get("quantity") != ib_qty:
                continue
            if m.get("unitPrice") != ib_price:
                continue

            m_date = parse_date(m.get("date"))
            if ib_date and m_date:
                delta = abs(ib_date - m_date)
                if delta > DATE_TOLERANCE:
                    continue
                if best is None or delta < best_delta:
                    best = m
                    best_delta = delta
            else:
                # No date to compare — still a candidate if no better match found
                if best is None:
                    best = m
                    best_delta = timedelta(days=99)

        if best:
            matched_pairs.append((ib, best))
            used_manual_ids.add(best["id"])
        else:
            unmatched_ibkr.append(ib)

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

        # Fetch fresh copy of manual activity for PUT payload
        url = f"{config['ghost_host']}/api/v1/activities/{m['id']}"
        fresh = requests.get(url, headers=headers(config["ghost_token"]), timeout=10)
        if fresh.status_code >= 400:
            log.error("  Cannot fetch manual activity %s (%d)", m["id"], fresh.status_code)
            errors += 1
            continue
        m_full = fresh.json()

        ok = put_comment(config, m_full, new_comment, dry_run=False)
        if ok:
            patched += 1
        else:
            errors += 1
            continue

        ok = delete_activity(config, ib["id"], dry_run=False)
        if ok:
            deleted += 1
        else:
            errors += 1

    log.info("")
    log.info("=== DONE ===")
    log.info("Patched: %d | Deleted: %d | Errors: %d", patched, deleted, errors)
    if errors:
        log.warning("Some operations failed — check logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
