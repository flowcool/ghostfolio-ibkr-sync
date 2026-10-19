# Proposal

## Why

A configured Flex Query can return a different IBKR account. The connector currently trusts the query-to-account list order and can import activities or update cash in the wrong Ghostfolio account.

## What Changes

- Read the source account from `AccountInformation.accountId` in every Flex report.
- Require at least one nonempty value, one unique value, and an exact match with the paired `IBKR_ACCOUNT_IDS` entry.
- Reject missing, mixed, or mismatched evidence before Ghostfolio target lookup and before every financial write.
- Keep other configured accounts running and fail the overall run through the existing account-failure outcome.
- Do not log the observed source account value.

Saved synthetic Flex reports in `tests/test_orchestration.py` establish this inventory:

| IBKR Flex record | Scope |
|---|---|
| `AccountInformation` | In: source-account evidence |
| `Trade` except CASH/OPT | Protected by the new gate; conversion unchanged |
| CASH/OPT `Trade` | Out: remains ignored |
| DETAIL dividend, payment-in-lieu, and withholding `CashTransaction` | Protected by the new gate; conversion unchanged |
| Other `CashTransaction` types or levels | Out: remain ignored |
| `ChangeInDividendAccrual` | Protected by the new gate; association unchanged |
| BASE_SUMMARY `CashReportCurrency` | Protected by the new gate; cash parsing unchanged |
| Other `CashReportCurrency` rows | Out: remain ignored |
| `AssetSummary` | Out: remains ignored |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `connector-runtime`: bind each Flex report to its configured IBKR source account before destination selection or writes.

## Non-goals

Change query ordering, Ghostfolio account selection, import conversion, deduplication, cash semantics, ENV names, authentication, notifications, publication, deployment, or sibling repositories.

## Impact

One pure XML parser, account orchestration, synthetic tests, and the connector runtime specification change. A failing report writes nothing. Rollback reverts the corrective PR.
