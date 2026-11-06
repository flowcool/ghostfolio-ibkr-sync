# Proposal

## Why

The RC2 burst gate measured an 18.19-second request-bound Ghostfolio background
chain in the golden lab. The qualified 15-second delay therefore fails with no
candidate defect. A new RC must carry a delay with margin before stable
promotion.

## What changes

- Keep the shared correction limit at five per connector run.
- Set the fixed inter-correction delay to 28.0 seconds.
- Record that 28.0 seconds is 1.5 times the measured 18.19-second maximum,
  rounded up. Revise it in a new release if a lab measures a longer chain.
- Keep sequential PUTs, exact readback, journal v3, stop-on-uncertainty and the
  no-resend rule unchanged.
- Re-run the exact RC3 regression and burst gate in both labs before stable use.

| Flex record | Scope |
| --- | --- |
| AccountInformation | Verify source account |
| Trade, supported STK | Date-only correction candidates |
| Trade, CASH/OPT | Excluded |
| CashTransaction, Dividends/PIL | Existing payment evidence |
| CashTransaction, Withholding Tax | Existing tax evidence |
| CashTransaction, Other Fees/Deposits/Withdrawals/Broker Interest Paid | Excluded |
| ChangeInDividendAccrual | Existing quantity evidence |
| CashReportCurrency | Existing cash path; no review correction |
| ConversionRate | No new FX conversion |
| CorporateAction | Excluded from this delay change |

## Non-goals

No limit increase, ENV override, Ghostfolio version or digest gate, production
write, stable tag or historical conversion is included.
