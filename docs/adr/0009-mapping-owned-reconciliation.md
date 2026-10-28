# Trust configured account mapping for bounded reconciliation

Date: 2026-10-28. Status: accepted.

## Context

Historical trade comments contain a tradeID without the source account. Current v2 comments include that account. ADR 0002 describes the old global suppression rule. Earlier activity review refused runtime migration because report windows cannot prove historical cross-account coverage.

This protects against an unknown historical account association. It also prevents a normal reference migration when the operator has explicitly configured the account relationship.

## Decision

The operator owns the IBKR-to-Ghostfolio account mapping and the historical activities assigned to it. The connector uses that mapping as the ownership authority. It does not certify lifetime ownership or global tradeID uniqueness.

The connector validates current source provenance, mapped destination ownership, recognized references and observed conflicts. A unique eligible legacy reference can migrate without historical cross-account proof. Comment-only migration preserves all other fields. Rebuild account-scoped import selection after confirmation; removing global suppression can expose another configured account's event to ordinary import checks.

Automatic correction requires an explicit non-off reconciliation profile. A profile defines accepted date and gross differences. Conservative requires a recognized unique reference; balanced and permissive can authorize mutually unique unreferenced matches. It does not turn a threshold match into exact identity proof. Fees do not establish identity. BUY/SELL quantities remain exact. Duplicate or conflicting current evidence cannot be overridden by a profile. Every write retains the qualified budget, durable intent, exact readback and uncertainty fence.

This implemented exception extends ADR 0003. Stable publication and production activation retain their separate GO. Manual review and separately authorized historical maintenance remain available. The full behavior is specified in [profiled-activity-reconciliation](../../openspec/changes/archive/2026-10-28-profiled-activity-reconciliation/proposal.md).

## Alternatives considered

- Require complete historical inter-account proof. This retains the current rule but makes routine naming changes depend on unavailable history.
- Trust every similar amount or date. This removes too much identity control and can choose between competing events.
- Trust explicit mapping and enforce bounded unique matches. This assigns configuration responsibility to the operator and observed-integrity responsibility to the connector.

## Consequences

An incorrect mapping can assign a historical reference to the wrong source account. The operator accepts this configuration risk. The connector still reports detected contradictions and refuses ambiguous automatic writes.

Profile matches can be wrong even when unique. Defaults remain manual. Limits and authority remain visible. Profile changes do not resolve uncertain requests. Software rollback does not restore activity data.
