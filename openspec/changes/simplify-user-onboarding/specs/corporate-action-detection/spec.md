# Documentation Location Delta

## MODIFIED Requirements

### Requirement: Automatic report rotation and safety evidence retention

The connector SHALL retain ordinary acquired reports for a fixed 30 days, measured as 720 hours from durable UTC acquisition time. On the next normal run after expiration, it SHALL automatically retire reports that are not required safety evidence. This SHALL also apply in simulation: local evidence maintenance is allowed, financial writes remain forbidden. There SHALL be no new retention ENV setting, byte quota, object-count ceiling or separate maintenance command. A period without executions does not run background cleanup. Re-reading an existing acquisition or changing its file timestamps SHALL NOT renew its age. Invalid, missing or future acquisition timestamps SHALL NOT justify early removal. Existing evidence without trustworthy acquisition time SHALL receive a single durable migration observation time and the full 30-day grace period.

The connector SHALL retain a selective set of complete original XML reports, acquisition bindings and official date documents while needed for import safety. Preserve every known event and unresolved conflict, including unsupported shapes and revised or cancelled evidence. Preserve the report context, trade chain, independent opening quantities, identity associations and continuous declared coverage needed to reconstruct and revalidate those events. A closed position, matching holding, prior reconciliation, manual acknowledgment or shorter current window SHALL NOT alone make evidence redundant. Retained evidence SHALL remain reparsable and hash-verifiable. Derived summaries or an observed current decision alone SHALL NOT replace required originals.

Automatic maintenance SHALL remove redundant acquisitions from the safety set only after proving that the surviving source evidence preserves these facts and the necessary reconstruction. Identical facts in overlapping reports SHALL NOT cause permanent retention of every daily copy. Archive expiry SHALL NOT manufacture new coverage, erase a known event/conflict or release a hold. When safe retirement cannot be proved, preserve the uncertain evidence and report the limitation. Ordinary archive size and retained safety work SHALL not grow with repeated acquisitions alone after the retention window. Safety storage MAY grow with distinct useful events, changed evidence and their required chains; no fixed total disk bound is claimed.

Maintenance SHALL use the existing writer lock, safe paths and durable atomic publication. Publish and verify surviving references before removing eligible files. A restart at any stage SHALL preserve all required originals and recover a complete committed reference set. Cleanup retries SHALL be idempotent. State recovery SHALL distinguish intentional retirement from lost required evidence; it SHALL NOT restore retired references merely by finding an obsolete binding. Automatically remove only connector-owned evidence that is not a configured input or an external alias. Rotation SHALL NOT affect mappings, official input documents, Ghostfolio data, activity-review proposals or correction journals. In particular, pending or confirmed financial journals SHALL not expire through this policy.

Failure of maintenance alone SHALL log a clear warning and enter the existing consolidated notification when configured. It SHALL NOT change exit status or suspend BUY/SELL if all required current and historical evidence remains valid and durable. It SHALL retry on the next run. Failure to acquire, validate, persist or recover required safety evidence SHALL retain the existing affected BUY/SELL hold and failure result. Independent cash and unrelated destinations SHALL retain their existing guards. No failed cleanup SHALL trigger a financial resend or a state reset.

Reconciliation SHALL retain its existing diagnostic logs and proposals. The user handles manual cleanup and reruns analysis. There SHALL be no new persistent reconciliation job, inactivity timeout, automatic archive replay or automatic protection of a user investigation. README SHALL link directly to the corporate-action guide. That guide SHALL explain the fixed retention period, safety exceptions, local maintenance in simulation, failure behavior and the need to keep a private copy or obtain another broker export for longer investigations. It SHALL NOT claim lifetime history or recovery of expired archives. New logs and notifications SHALL preserve existing redaction rules.

Baseline: candidate README states full report retention grows with acquisitions; the retained-evidence tests verify originals and recovery but implement no expiry. Activity review builds current source events and keeps its own proposal and correction journal. Commands below specify future offline acceptance, not current passing evidence.

#### Scenario: Fixed age and legacy adoption
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k retention_age` exercises 719 hours, exactly 720 hours, repeated acquisitions, restarts, modified file times, simulation, future or invalid timestamps and legacy objects without timestamps
- **THEN** ordinary reports expire only from durable acquisition age, no configuration or volume ceiling is introduced, migration receives one full grace period and no financial write occurs.

#### Scenario: Safety evidence survives ordinary expiry
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k retention_safety` ages event reports, revisions, unknown actions, optional position anchors and trade/coverage chains past 30 days, including closed positions, manual reconciliation, changed mappings and events outside the current window
- **THEN** required complete originals and bindings survive, known facts and conflicts remain reconstructible, redundant daily copies can retire, and original versus maintained evidence gives the same justified candidate holds and exact effective quantities.

#### Scenario: Durable cleanup and failure isolation
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k retention_recovery` interrupts reference publication and each cleanup stage, restarts, loses mutable state, changes files concurrently, fills storage, denies unlink, or supplies unsafe paths and configured-input aliases
- **THEN** committed evidence remains recoverable, retired references stay retired, unsafe inputs and journals remain byte-identical, cleanup retries safely, and only unavailable required proof creates a financial hold or failure status.

#### Scenario: Years of unchanged facts
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k retention_longevity` simulates at least ten years of daily rolling reports with changing generation times, plus shorter high-frequency runs and sparse new events/revisions
- **THEN** ordinary files follow the 30-day window, unchanged safety facts do not retain a new permanent XML for every acquisition, runtime reconciliations parse only required evidence and the current source, and genuine new facts remain visible without an inevitable age/count/size stop.

#### Scenario: Maintenance reporting and manual reconciliation
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k retention_reporting` covers maintenance-only failure, missing required proof, disabled/enabled Apprise, simulation and unchanged manual review proposals/journals
- **THEN** warnings join at most one redacted summary per completed run, maintenance-only failure leaves otherwise valid trading and exit status unchanged, proof failure retains its fence, and no reconciliation job or journal expiration is introduced.
