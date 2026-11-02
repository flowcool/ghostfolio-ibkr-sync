# Design

## Context

See proposal.md. `record_action` already deduplicates private event keys per reason. `_finalize_notification` currently sends each observed action every run. Corporate holds also remain eligible every run.

## Decisions

- Use sorted reason/count pairs as the stable grouped fingerprint. Any count decrease is also material. Replacing an event under the same reason/count does not send a notice. A cleared reason sends a zero-count line, including when the last reason clears. This is a resolution notice.
- Use a fixed seven-day interval from the last confirmed action-summary delivery. This validated default needs no ENV override. Reuse `file_bytes`, `safe_path`, `atomic_yaml`, `fingerprint` and `private_directory`. Store schema, context hash, counts, fingerprint and successful-send time in `CORPORATE_ACTION_STATE_FILE.required-actions.yaml`. Use a separate lock and generation check. Include no event identities or credentials.
- Missing, corrupt, unsafe or unwritable delivery state keeps actions eligible and logs a fixed warning. Failed, timed-out or interrupted delivery does not advance the clock. Failed cycles never replace a successful action snapshot because acquisition can be incomplete.
- Keep `_finalize_notification` as the single dispatch. Failure remains immediate. Unchanged corporate holds use grouped action scheduling on successful cycles; first/changed informational findings and verified resumptions keep `plan_notifications` behavior.
- `report_review_outcome` distinguishes missing proof from execution qualification. Approved or profile-eligible normal work with valid proof is deferred when only qualification or the run budget prevents execution. Maintenance and uncertain requests remain actions.

## Risks / Trade-offs

- Same-count membership changes wait for the reminder. Private evidence remains complete.
- A crash after send can repeat a notice. Confirm only after transport success.
- Concurrent generations can repeat a notice. Never overwrite changed state.

## Migration Plan

The first eligible run creates separate delivery state under the existing private mount. No financial-state migration occurs. Revert the code commit to restore per-run notices. Retain companion files and financial evidence. Release and deployment need separate work.
