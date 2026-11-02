# RC activity-review burst qualification

This procedure validates the connector RC behavior. Run it
once in `a-ghostfolio-lab` and once in `a-ghostfolio-lab-golden`. Use the
versioned infra entry point from the selected stack directory. Reserve the lab,
record the operation reference, and stop the instance after the run.

The RC permit is five corrections with a 15-second minimum delay. Stable
promotion requires PASS in both instances on the same connector digest. This
procedure does not authorize stable publication or production writes.

Qualification covers connector behavior. Each release records the Ghostfolio
version observed in its labs as information. A Ghostfolio version or image change
does not invalidate qualification. If a future background chain exceeds the delay,
exact readback and stop-on-uncertainty still protect the data. Raise the delay in
a new connector release.

## Prepare six date-only corrections

Use one lab account and six source events from one Flex query. Each destination
activity must have the exact v2 comment identity of one source event. Set its
stored date to one local calendar day before the source date. Keep quantity,
price, fee, currency, symbol, tags and account unchanged. Use six distinct
events. Do not create a quantity, symbol or account correction in this fixture.

The six rows can be created with the Ghostfolio activity API. Run the following
from the selected infra stack directory. `GHOST_ACCESS_TOKEN` and
`GHOST_ACCOUNT_ID` are private lab values. Do not print them or commit them.

```sh
export GHOST_HOST='http://127.0.0.1:3335'
export GHOST_ACCESS_TOKEN='read-from-the-selected-lab-token-file'
export GHOST_ACCOUNT_ID='selected-lab-account-id'

for n in 1 2 3 4 5 6; do
  curl --fail-with-body --silent --show-error \
    -H "Authorization: Bearer ${GHOST_ACCESS_TOKEN}" \
    -H 'Content-Type: application/json' \
    -d "{\"accountId\":\"${GHOST_ACCOUNT_ID}\",\"type\":\"BUY\",\"symbol\":\"AAPL\",\"dataSource\":\"YAHOO\",\"currency\":\"USD\",\"quantity\":1,\"unitPrice\":2,\"fee\":0,\"date\":\"2026-01-0${n}T12:00:00Z\",\"comment\":\"IBKR#v2#LAB:TRADE:T${n}\",\"tags\":[]}" \
    "${GHOST_HOST}/api/v1/activities" >"seed-${n}.json"
done
```

The source Flex fixture must contain `T1` through `T6` with dates one local day
later than the six rows. Run the normal connector in simulation mode first:

```sh
python3 ghostfolio/scripts/lab.py connector-run --instance "$INSTANCE" --dry-run true
```

Open the private `ACTIVITY_REVIEW_FILE` produced by that run. Set `approve: yes`
for `T1` through `T6`. The sixth approved proposal must remain deferred
by the shared budget. Keep the review file at mode 0600.

## Observe each PUT and its background jobs

The infra runner already provides the exact observer used by the 2026-10-23
isolated proof. Start it before the real connector run. The observer reads only
the ordered Redis `MONITOR` stream. It retains allowlisted Bull job metadata and
completion events. It sends no Redis or financial write.

```sh
INFRA_REPO="${INFRA_REPO:?path to the checked-out infra repository}"
RUN_DIR="${RUN_DIR:?private run directory}"
docker compose exec -T ghostfolio node -e "$(cat "${INFRA_REPO}/scripts/lib/ghostfolio_lab/review_jobs.js")" \
  | tee "${RUN_DIR}/burst-observer.ndjson"
```

In a second terminal, run the exact RC image with writes enabled:

```sh
python3 ghostfolio/scripts/lab.py connector-run --instance "$INSTANCE" --dry-run false
```

For each of the five PUTs, correlate the connector request timestamp with the
observer events. Accept a correction only when all of these events exist after
that PUT response:

1. `DATA_GATHERING_QUEUE` / `GATHER_HISTORICAL_MARKET_DATA` for the corrected
   symbol reaches `completed`.
2. A new `PORTFOLIO_SNAPSHOT_COMPUTATION_QUEUE` / `PORTFOLIO` job for the owner
   reaches `completed` after the market job and the PUT response.

Record `market_seconds` and `portfolio_seconds` for every PUT. Define `D` as
the largest PUT-response-to-portfolio-completion value. Add the documented
qualification margin to `D` when accepting a delay. The five requests must be
sequential, each must have exact activity readback before the next PUT, and the
observed spacing must be at least 15 seconds. The sixth activity must remain
unchanged and its approval must remain deferred. No later import or cash write
may follow an uncertain correction.

The current runner command that exercises the observer contract directly is:

```sh
python3 ghostfolio/scripts/lab.py qualification-review --review-jobs \
  --operation-ref APPROVED_PHASE \
  --qualification-input SEED_RESULT_JSON --input-sha256 SEED_RESULT_HASH \
  --probe-row SEEDED_TRADE_ID --probe-row SEEDED_DIVIDEND_ID \
  --observe-seconds 0 --observe-seconds 1 --observe-seconds 5 \
  --product-checkout CLEAN_PRODUCT_CHECKOUT --product-python PRODUCT_INTERPRETER \
  --package-manifest PRODUCT_PACKAGE_JSON --package-sha256 PRODUCT_PACKAGE_HASH \
  --output NEW_REVIEW_DIRECTORY
```

That command proves the per-PUT observer and exact readback. The six-row normal
run above proves the active five-request permit and the deferred sixth proposal.
Keep the private observer output and connector evidence with the lab acceptance
record. If any background chain exceeds the 15-second permit, or if any result
is uncertain, mark the RC FAIL. Revise the values in a new RC before stable
promotion. Never retag the failed RC.
