#!/usr/bin/env bash
# Block git commit if ibkr_to_ghostfolio.py has syntax errors
python3 -m py_compile ibkr_to_ghostfolio.py 2>&1
exit_code=$?
if [ $exit_code -ne 0 ]; then
  echo "BLOCKED: ibkr_to_ghostfolio.py has syntax errors — fix before committing."
  exit 2
fi
