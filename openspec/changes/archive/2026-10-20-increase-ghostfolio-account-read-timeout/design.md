## Decision
Use 120 seconds for requests.get in ghost_get_accounts and ghost_update_cash_balance. These are the two account reads that currently use 30 seconds. Keep the existing requests scalar timeout convention. This is a socket inactivity timeout, not a total run deadline.

## Safety
Keep cash PUT at 30 seconds. Keep activity GET at 60 seconds, authentication unchanged, redirects disabled and no account-read retry. A read timeout must still propagate before cash PUT, including in simulation. The operator requested this timeout increase and authorized a later replay. No live call is part of this implementation.

## Verification and rollback
Run bash scripts/check.sh with mocked HTTP. Assert successful account reads use 120 seconds and cash writes retain 30 seconds. Assert a read timeout causes one GET and no PUT. Revert the code commit to restore the previous timeouts.
