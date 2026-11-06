# RC activity-review long-chain qualification

Qualify the exact connector RC digest in both `a-ghostfolio-lab` and
`a-ghostfolio-lab-golden`. Use the versioned Infra lab runner from the selected
stack directory. Reserve both labs in the operation issue. Retain private proof.
Use the floating default Ghostfolio image. Record its version as information.
Stop each instance after use. Verify the stop before releasing its reservation.

## Acceptance

Each run applies all eligible approved corrections. There is no count cap.
The fixed minimum inter-correction delay is D=28 seconds. No ENV setting can
lower D or add a count cap. There is no additional run duration bound.
Allow at least `(corrections - 1) * 28` seconds plus request and readback time.
Keep writers exclusive. The test transport needs a documented timeout long
enough for the full fixture. Its exact payload allowlist must reject a resend.

Run these scenarios in each lab on the same immutable candidate:

1. First-install or golden-upgrade regression. Cover effective activity currency,
   EST/EDT dates, journal v3 and recovery of an older null-currency request.
2. At least 30 date-only corrections in one account. Apply them in one run.
3. At least 30 date-only corrections across two accounts. Apply all in one run.
4. At least 30 approved corrections with a controlled readback fault in the
   middle. Stop at that correction. Keep later approvals and journal v3.
   Send no later correction, import or cash request. Send no request again.

Use synthetic source events with exact v2 references. Seed each destination
date one local calendar day before its source date. Keep account, currency,
quantity, price, fee, symbol, tags and notes unchanged. Preview without writes.
Approve only the exact fixture corrections in the private review file.

## Measure each request

Start the versioned read-only Redis observer before the connector. Do not use
the observer to pace the connector. Record actual request and response times.
For each PUT, identify the new matching historical market-data job and the later
completed owner portfolio job. Record market and full chain time.

Require every response-to-next-PUT gap to be at least D. Require the full
request-bound background chain to be at most D/1.5 seconds (18.667 seconds).
Prove exact activity readback before every next PUT. Compare complete stored
activity fields and native cash with the baseline and exact correction plan.
The repeat process must send no write. Keep all timing samples privately.

For the controlled fault, retain the pending journal and independent exact
readback before any recovery. Simulation must not consume the pending request.
Only after exact expected-after evidence resolves the uncertainty may a new
process continue the remaining approved corrections. It must not resend a prior
PUT. Keep this recovery phase explicit in the operation plan.

## Verdict

A missing readback, observer completion, timing margin or retained approval is
FAIL. Stop on uncertainty. Retain proof and never resend automatically. If the
background margin fails, propose a higher D in a new connector RC. Never retag
an unsuccessful RC. Stable publication and production need separate authority.

Attach `lab-qualification.json` to a passing prerelease. Bind the connector tag,
commit and digest, both PASS results, scenario timings and verified final stops.
Do not include secrets, private paths or account identifiers in public proof.
