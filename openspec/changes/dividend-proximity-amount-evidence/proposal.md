## Why

After the connector imports a dividend, a different payment of the same security within 3 days is skipped silently. The run reports success and the payment is lost from Ghostfolio. The cause: the proximity check counts the connector's own `dividend#…` rows, although exact comment identity already covers them. A real case is not proven: saved real reports hold 0 payment pairs within 3 days (smallest gap 88 days). The defect is latent and was found by code review.

## What changes

- Rows with a connector comment (`dividend#…`) no longer enter the proximity check. Two distinct payments on consecutive days are both imported.
- Proximity still skips a payment near a manual or legacy row. The skip is now visible: equal gross logs INFO; different gross logs one WARNING with both dates, both gross values and "check manually".
- The dry-run diagnostic follows the same rule and shows both gross values for `skipped by proximity`.
- ADR 0002 and the README limits are updated.

## Scope

| Flex record type | Position |
|---|---|
| CashTransaction Dividends / Payment In Lieu Of Dividends (DETAIL) | In scope: dedup only, conversion unchanged |
| CashTransaction Withholding Tax (DETAIL) | Out of scope: unchanged |
| ChangeInDividendAccrual | Out of scope: unchanged |
| Trade, CashReport, other cash types | Out of scope |

Checked on saved real Flex reports: 55 dividend rows, 34 securities.

## Non-goals

- No automatic import of "near date, different gross" payments: the legacy rows in Ghostfolio were never measured (they may hold net or converted amounts). Follow-up: measure them with a read of the destination, then revisit.
- No change to exact comment identity, tolerance of ±3 days, exit codes or notifications.
- Revised amounts on the same day (infra-8tt.36) stay a separate change.
- No update or deletion of existing activities.
