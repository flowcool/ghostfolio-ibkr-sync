## ADDED Requirements

### Requirement: Current source preview for unavailable targets

When a normal-run proposal retains a target that current discovery cannot use,
review SHALL show an explicit unavailable-target status.
If the current source exists, proposed values SHALL come from that current source.
They SHALL NOT retain an obsolete proposed date from a former cycle.
Current target values SHALL remain last-observed evidence only.
Comparisons that need a current target SHALL be empty.
The row SHALL remain non-actionable, with blank consent and no profile authority.
The candidate key SHALL remain stable.
Existing pending source holds SHALL remain until fresh positive evidence permits release.
Existing rejected-pair absence rules and journal recovery SHALL remain unchanged.

#### Scenario: Repeated refresh and compact recovery

- **WHEN** `python -m pytest -q tests/test_activity_review.py -k unavailable_target` runs synthetic changed-source cases through repeated refresh, compact entry deletion and restart
- **THEN** the visible preview shows current source values, keeps blank consent and the pending source hold, and cannot restore stale correction authority.

#### Scenario: Fresh endpoint evidence controls the outcome

- **WHEN** `python -m pytest -q tests/test_activity_review.py -k unavailable_target` covers absent source, returning target, satisfied target and reassigned target
- **THEN** absent source stays suspended, a returning target gets fresh evidence without old consent, and satisfied or positively reassigned targets follow the existing hold-release rules.
