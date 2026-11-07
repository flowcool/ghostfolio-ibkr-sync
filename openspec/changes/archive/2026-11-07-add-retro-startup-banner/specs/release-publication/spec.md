## ADDED Requirements

### Requirement: Retro Docker startup banner

The Docker entrypoint SHALL print a fixed ASCII `IBKR SYNC` banner with an `IBKR -> Ghostfolio` subtitle once per container start. It SHALL print the existing dynamic version and commit line immediately below the banner. It SHALL support one-off and CRON startup without a runtime rendering dependency, network lookup, terminal escape sequence or new setting. Scheduled application cycles SHALL retain their existing identity output without repeating the banner.

Baseline: `entrypoint.sh` prints the release identity before selecting its mode; `tests/test_entrypoint.py` covers this identity and synthetic scheduler startup. `app.main()` prints the identity for each application cycle.

#### Scenario: One-off and scheduled startup show the banner

- **WHEN** `.venv/bin/python -m pytest -q tests/test_entrypoint.py` runs with synthetic executables
- **THEN** both startup modes show one banner and the dynamic identity below it, with no terminal escape code, and existing scheduler, failure and exit-code checks pass.
