# Fail the account before any write when a Flex prerequisite is missing

Date: 2026-10-14. Status: accepted.

A required Flex prerequisite that is missing fails that account with one ERROR
naming the missing item. The item can be the time-zone suffix on dividend,
payment-in-lieu and withholding times, a required Cash Transactions or Dividend
Accruals attribute, or the Account Information currency. The failure uses the
normal failure outcome and does not enable `DRY_RUN`. The other accounts still
run. An empty report passes: a report without relevant dividend rows needs no
suffix or attribute. `DRY_RUN` runs the same checks and previews the same
failure.

The time-zone suffix and the dividend attributes are checked before any
Ghostfolio financial write, including cash and platform updates. The base
currency is checked at the cash stage, after the import phases, so trades and
dividends are unaffected; no balance is sent. A single empty or malformed value
in a present attribute keeps its local rejection and does not fail the account.

A silent partial run was the alternative. It let data go stale, or refused a
later dividend with only a warning, without any signal. A real dry run on a
query without `conid` exited 0 and logged nothing. Failing up front turns a
Flex query defect into a visible account failure that names the field to tick.

Consequence: removing a time-zone suffix, a required attribute or the currency
from the Flex query is a breaking change. Query changes need the steps in
[Upgrading to 3.0](../upgrading-to-3.0.md).

Sources: the requirements "Timezone prerequisites and parser compatibility",
"Dividend field prerequisites" and "Cash target guard" in the
[connector-runtime spec](../../openspec/specs/connector-runtime/spec.md), and the
archived changes
[make-dividend-diagnostics-actionable](../../openspec/changes/archive/2026-10-14-make-dividend-diagnostics-actionable/proposal.md),
[fail-account-on-missing-dividend-fields](../../openspec/changes/archive/2026-10-14-fail-account-on-missing-dividend-fields/proposal.md) and
[guard-cash-target](../../openspec/changes/archive/2026-10-14-guard-cash-target/proposal.md).
