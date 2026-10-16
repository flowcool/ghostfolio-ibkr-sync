# Tasks

## 1. Calendar-day grouping

- [x] 1.1 Group ambiguous fills with the parsed `YYYY-MM-DD` while preserving side, ticker, and ISIN; add compact and dashed same-day coverage plus a dashed different-day regression. Check: `.venv/bin/python -m pytest -q tests/test_filters.py -k 'split_fills'`.

## 2. Integration

- [x] 2.1 Validate the OpenSpec change and run the complete repository gate. Check: `openspec validate group-split-fills-by-calendar-day --strict && scripts/check.sh`.
