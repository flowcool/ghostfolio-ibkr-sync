# Tasks

## 1. Flex source-account gate

- [x] 1.1 Parse and validate `AccountInformation.accountId` before Ghostfolio target lookup or writes. Add synthetic coverage for matching, missing, blank, mixed, mismatched, duplicate matching, and swapped multi-account reports. Verify with `.venv/bin/python -m pytest -q tests/test_parsing.py tests/test_orchestration.py -k 'source_account' && scripts/check.sh && openspec validate reject-wrong-flex-source-account --strict`.
