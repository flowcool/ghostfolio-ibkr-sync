# Tasks

Implementation follows the approved GO in the owning work item. Stable publication
and production remain outside this change.

- [x] 1. Set the shipped permit to five corrections and 28.0 seconds. Update
  the default-permit test.
- [x] 2. Update the activity-review guide, release guide, burst procedure,
  CHANGELOG and activity-review specification with the 18.19-second measurement,
  1.5x margin and new-release revision rule.
- [x] 3. Add this OpenSpec delta and validate it.
- [x] 4. Run the full pytest suite and `bash scripts/check.sh`.
- [x] 5. Publish one PR, merge it, cut RC3 and run both lab burst gates. Record
  the result in the owning work item. RC3 passed both lab burst gates; stable v4.2.0
  reuses its digest. The later `remove-correction-count-cap` change superseded
  the five-correction permit, so this change archives without a spec sync.
