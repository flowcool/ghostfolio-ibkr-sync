## Why

After the connector imports a dividend, a different payment of the same security within 3 days is skipped silently. The run reports success; the payment is lost. The cause: the proximity check counts the connector's own `dividend#…` rows, although exact comment identity already covers them. No real case is proven (0 pairs within 3 days in saved reports; smallest gap 88 days). The defect is latent.

## What changes

- Rows with a connector comment (`dividend#…`) no longer enter the proximity check. Consecutive-day payments are both imported.
- Proximity still skips a payment near a manual or legacy row. The skip is now visible: equal gross logs INFO; different or not comparable gross logs one WARNING with dates, gross, fee and the operator action (check IBKR, add by hand if distinct).
- The dry-run diagnostic follows the same rule and shows both gross values.
- ADR 0002 and the README limits are updated. They state the trust principle: a row with a connector comment is ours and trusted by exact identity; a user edit of such a row is out of contract.

## Scope

In scope: CashTransaction Dividends and Payment In Lieu Of Dividends (DETAIL), dedup only; conversion unchanged. Out of scope: Withholding Tax, ChangeInDividendAccrual, Trade, CashReport and other cash types. Checked on saved real reports: 55 dividend rows, 34 securities.

## Non-goals

- No automatic import of "near date, different gross" payments: legacy rows were never measured (they may hold net or converted amounts). Follow-up: measure them by a destination read.
- No change to exact comment identity, ±3 days, exit codes or notifications.
- Same-day revised amounts (infra-8tt.36): separate change.
- No update or deletion of existing activities.
