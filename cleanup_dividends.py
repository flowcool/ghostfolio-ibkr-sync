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

CRITICAL SAFETY: everything deleted is logged in full to cleanup_div_YYYYMMDDTHHMMSS.json
before any mutation — sufficient for reinjection via POST /api/v1/import.
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
    return resp.json().get("activities", [])


def parse_date(iso):
    if not iso:
        return None
    iso = iso.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso)
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


def symbol_of(activity):
    return (activity.get("SymbolProfile") or {}).get("symbol", "")


def put_comment(config, activity, new_comment, dry_run):
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


def main():
    parser = argparse.ArgumentParser(description="Clean up duplicate dividend activities")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry-run)")
    args = parser.parse_args()
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

    # Split dividend# (IBKR-synced) vs manual dividends
    div_ibkr = []   # comment starts with "dividend#"
    div_manual = [] # type=DIVIDEND, comment does NOT start with "dividend#"
    for a in all_activities:
        if a.get("type") != "DIVIDEND":
            continue
        comment = a.get("comment") or ""
        if comment.startswith("dividend#"):
            div_ibkr.append(a)
        else:
            div_manual.append(a)

    log.info("dividend# entries (IBKR-synced): %d", len(div_ibkr))
    log.info("Manual dividend entries: %d", len(div_manual))

    # For each dividend# entry, find a matching manual entry
    matched_pairs = []   # (ibkr_entry, manual_entry)
    unmatched_ibkr = []
    used_manual_ids = set()

    for ib in div_ibkr:
        ib_sym = symbol_of(ib)
        ib_qty = ib.get("quantity")
        ib_price = ib.get("unitPrice")
        ib_date = parse_date(ib.get("date"))

        best = None
        best_delta = None

        for m in div_manual:
            if m["id"] in used_manual_ids:
                continue
            if symbol_of(m) != ib_sym:
                continue
            if abs(m.get("quantity", 0) - ib_qty) > 1e-9:
                continue
            if abs(m.get("unitPrice", 0) - ib_price) > 1e-9:
                continue

            m_date = parse_date(m.get("date"))
            if not ib_date or not m_date:
                log.warning("  Skipping candidate %s — unparseable date", m["id"])
                continue
            delta = abs(ib_date - m_date)
            if delta > DATE_TOLERANCE:
                continue
            if best is None or delta < best_delta:
                best = m
                best_delta = delta

        if best:
            matched_pairs.append((ib, best))
            used_manual_ids.add(best["id"])
        else:
            unmatched_ibkr.append(ib)

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

    # Dump full snapshot before any mutation — sufficient for reinjection
    log_file = Path(f"cleanup_div_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json")
    safety_records = []
    log.info("Safety log will be written to %s (per-pair, before each mutation)", log_file)

    log.info("")
    log.info("=== APPLYING CHANGES ===")
    patched = 0
    deleted = 0
    errors = 0

    for ib, m in matched_pairs:
        new_comment = ib.get("comment")
        log.info("Processing %s qty=%s price=%s...", symbol_of(ib), ib.get("quantity"), ib.get("unitPrice"))

        # Fetch fresh copy of manual activity for PUT payload
        url = f"{config['ghost_host']}/api/v1/activities/{m['id']}"
        fresh = requests.get(url, headers=headers(config["ghost_token"]), timeout=10)
        if fresh.status_code >= 400:
            log.error("  Cannot fetch manual activity %s (%d)", m["id"], fresh.status_code)
            errors += 1
            continue
        try:
            m_full = fresh.json()
        except Exception as e:
            log.error("  Cannot parse response for %s: %s", m["id"], e)
            errors += 1
            continue

        # Write safety record AFTER fresh fetch, BEFORE any mutation
        safety_records.append({
            "action": "PUT_comment_on_manual",
            "manual_fresh": m_full,
            "ibkr_to_delete": ib,
            "new_comment": new_comment,
        })
        log_file.write_text(json.dumps(safety_records, indent=2, default=str))

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
