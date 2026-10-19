# Design

## Context

See `proposal.md`. `docs/ibkr-setup.md` already requires `ClientAccountID` in Account Information. `process_account` fetches the report, then selects the Ghostfolio target without checking that evidence.

## Goals / Non-Goals

**Goals:** Stop a missing, mixed, or different Flex source account before target lookup, imports, or cash updates. Keep the observed account value out of logs.

**Non-Goals:** Change multi-account ordering, destination names, record conversion, deduplication, cash independence after a valid gate, or public configuration.

## Decisions

1. Add `parse_source_account_ids` to `ibkr.py`. It reuses `xml.etree.ElementTree`, strips values, and returns `None` if no `AccountInformation` row exists or any row lacks a nonempty `accountId`. Otherwise it returns the unique values. Duplicate rows for one account remain valid.
2. Call the parser in `process_account` immediately after `fetch_flex_report`. Exact equality with `{ibkr_account_id}` is the only passing result. This position prevents even the Ghostfolio target read and all later writes.
3. Log only `missing`, `mixed`, or `mismatched` evidence with the query identifier. Do not include the observed report account.
4. Reuse the existing local account failure path. Later configured accounts still run, and the overall run exits 1.
5. Extend the existing synthetic orchestration fixtures. Tests assert zero target lookup, import, and cash calls for missing, blank, mixed, and mismatched evidence, plus success for duplicate matching evidence and isolation across swapped queries.

## Risks / Trade-offs

- A Flex Query without Account Information now fails. The setup guide already requires `ClientAccountID`; failing is safer than guessing.
- Multiple identical Account Information rows are accepted because they prove one source account.

## Migration Plan

Users with compliant queries need no change. A rejected query must add `ClientAccountID` or correct its account selection. Roll back by reverting the corrective PR.
