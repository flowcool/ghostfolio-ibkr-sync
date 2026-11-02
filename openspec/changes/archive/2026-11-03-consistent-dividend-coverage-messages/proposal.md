# Proposal

## Why

The dividend dry-run report can classify a destination activity outside proven
source coverage as a manual correction. The same run also says that no user
correction is requested. The report summary and the required-action notification
then expose different counts for the same input.

## What Changes

- Treat an activity outside proven IBKR source coverage as information.
- Apply the same existing no-correction policy to named representation limits.
- Keep the activity visible in the detailed report with one `No action needed.`
  line.
- Exclude that activity from the `to check` count and the `dividend_check`
  notification.
- Keep concrete source/destination discrepancies as required manual actions.
- Add synthetic tests that compare the detailed report and notification action
  state for the same 15-item input.
- State the rule in the operator configuration guide.

## Scope

| Input | Scope | Use |
|---|---|---|
| `CashTransaction` dividend and withholding rows | In | Existing source dividend groups |
| `ChangeInDividendAccrual` rows | In | Existing quantity evidence |
| Ghostfolio dividend activities | In | Existing historical comparison |
| `Trade` | Out | Existing trade selection |
| `AccountInformation`, `CashReportCurrency` | Out | Existing account and cash processing |
| `CorporateAction` | Out | Existing corporate-action processing |

## Non-goals

- No import, cash, correction, deletion or identity behavior changes.
- No historical data repair.
- No release, tag or production operation.
