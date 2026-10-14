## ADDED Requirements

### Requirement: Proposed dividend match

Under DRY_RUN, every dividend item to check that has a candidate SHALL carry one "Proposed match" section, repeated in each block of the same IBKR dividend, including legacy-comment rows. The section SHALL show the IBKR dividend (reference, quantity, gross, fee) and the candidate Ghostfolio rows side by side, each row labelled Keep, Duplicate or Differs, and one action line naming the row to act on. Confidence SHALL be "strong" (same security, local day, gross and fee) or "weak" (same security and local day only, or dates inside the existing proximity window). The section SHALL pick one best candidate; with no candidate it SHALL read "no confident match". Weak proposals SHALL label no row Keep. The proposal SHALL NOT write, repair or change selection, classes, categories, summary counts, exits or notifications. Text SHALL use plain decimals.

Baseline: the DRY_RUN of 2026-10-14 gave 20 items to check, 9 informational and 1 noise.

#### Scenario: Strong match with a legacy twin
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'dividend_match_strong'` formats a canonical row and a legacy twin, both equal in gross and fee
- **THEN** both blocks show the IBKR side, the canonical row as Keep, the twin as Duplicate, "strong", an action naming the twin and "Nothing was written".

#### Scenario: Weak and absent
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'dividend_match_weak'` runs a one-unit gross gap, a quantity gap, a proximity-window row and a dividend without any candidate
- **THEN** the first three read "weak" with every row Differs and no Keep, and the last reads "no confident match".

#### Scenario: Display only
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'dividend_match_unchanged'` runs the same findings before and after
- **THEN** classes, categories, summary line and exits are equal, and no line contains `Decimal(` or an exponent.

#### Scenario: Real read-only acceptance
- **WHEN** the operator-authorized DRY_RUN on the production query runs with a private log
- **THEN** zero writes occur, every item to check shows a proposed match or "no confident match", and the summary reads 20 to check, 9 informational, 1 noise.
