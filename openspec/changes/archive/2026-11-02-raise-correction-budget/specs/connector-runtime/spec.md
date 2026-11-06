# Spec Delta

## MODIFIED Requirements

### Requirement: Destination comment compatibility gates

Qualification SHALL cover connector behavior. Ghostfolio image and version SHALL NOT be qualification dimensions. Each release SHALL record the Ghostfolio version observed in its labs as information. Production desired configuration uses mutable `latest`. Version or image drift SHALL NOT require renewed qualification. If a future background chain exceeds D, exact readback and stop-on-uncertainty SHALL still protect data; a new connector release SHALL raise D.

Pinned source observations:

- [Config](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/libs/common/src/lib/config.ts) sets `COMMENT_MAXIMUM_LENGTH` to 2000.
- [Create DTO](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/libs/common/src/lib/dtos/create-order.dto.ts) and [update DTO](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/libs/common/src/lib/dtos/update-order.dto.ts) validate an optional string, trim its ends and enforce that maximum. No comment character filter appears there. [Order schema](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/prisma/schema.prisma) has nullable String with no narrower declared column limit.
- [Import service](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/apps/api/src/app/import/import.service.ts) compares comment and financial fields without accountId; a changed comment can defeat server deduplication.
- [API setup](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/apps/api/src/main.ts) transforms and whitelists DTO fields and limits JSON bodies to 10mb. That request-size bound is separate from comment length.

The writer SHALL use only ASCII `[A-Za-z0-9._-]+` in account and source-ID segments. `#` and `:` SHALL appear only as grammar separators. For bare generated identities, full length SHALL be at most 2000 characters: `15 + len(account) + len(tradeID)` for TRADE, `18 + len(account) + len(actionID)` for DIVIDEND. Valid inputs need no trimming or Unicode length interpretation. Existing historical reader acceptance SHALL NOT acquire the writer's new length restriction. Reviewed comments with preserved notes SHALL require separate exact-image round-trip qualification of the combined 2000-character limit, encoding and DTO trimming. Unicode notes SHALL NOT be treated as Unicode identity segments. Failure to preserve notes SHALL make the correction non-actionable, never truncate user text.

G4 SHALL verify the image/source binding, realistic identity lengths, permitted punctuation and two-account otherwise identical payloads by exact byte-for-byte import/readback in an isolated synthetic lab. Local boundary tests SHALL cover 1999/2000/2001 against the source-backed 2000-character maximum; a lower arbitrary writer cap SHALL NOT replace that contract. Unicode, whitespace and reserved characters SHALL reject locally. Source inspection does not replace this pending round-trip gate.

#### Scenario: Comment boundaries
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_comment_limits` runs both identity kinds at 1999/2000/2001 characters with invalid separators, whitespace, Unicode and punctuation
- **THEN** only valid ASCII identities of at most 2000 characters become payloads; no transformation or legacy fallback occurs; invalid existing reserved comments still stop globally.

#### Scenario: Optional review compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_runtime_contract` exercises this requirement with review disabled, enabled and later disabled after a notes-bearing correction
- **THEN** the disabled baseline remains valid, the explicit review exception follows activity-correction-review, and all supported historical reference generations remain readable.

