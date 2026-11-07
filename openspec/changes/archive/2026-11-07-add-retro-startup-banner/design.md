## Context

`entrypoint.sh` prints the release identity before it selects one-off or CRON mode. `app.main()` reports identity for each application cycle. Existing `tests/test_entrypoint.py` uses synthetic executables and isolated files.

## Goals / Non-Goals

Add one compact banner per container start. Keep scheduled cycles unchanged. Add no runtime dependency, ENV setting, color or network call.

## Decisions

Use `pyfiglet` 1.0.4 with the MIT-licensed `slant` font to generate `IBKR SYNC` once during development. Store its five non-blank ASCII lines in a quoted shell heredoc in `entrypoint.sh`. Add an `IBKR -> Ghostfolio` subtitle. Keep the existing version and commit line immediately below it. The shell prints the banner before either mode starts. Existing stdout behavior stays unchanged.

Reuse `tests/test_entrypoint.py` as the acceptance boundary. Check one-off and scheduled startup, exact release identity, one banner, no terminal escape codes and unchanged failure behavior. Run the full offline suite once after the change.

## Risks / Trade-offs

Startup gains six lines. Log aggregation may prefix each line; the art stays aligned because each source line has the same prefix.

## Migration Plan

No migration. Revert the implementation commit or restore the previous qualified image digest. No state format or financial write changes.

## Open Questions

None.
