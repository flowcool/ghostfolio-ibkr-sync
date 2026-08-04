---
description: Security mindset for all changes
---

- SSRF: assertion on `base_url` prefix for IBKR step-2 — already fixed (PR #6), do not regress
- XML: `ET.fromstring` is safe (no XXE with ElementTree), but validate extracted fields
- Credentials (`IBKR_TOKEN`, `GHOST_TOKEN`): only from `os.environ`, never hardcoded or logged
- Any new external HTTP call → trigger `security-review` skill before merge
- Any change touching env var reading or XML parsing → trigger `security-review`
