# Upgrading to 2.2

Nothing is required: an existing 2.1 configuration keeps working unchanged. Two optional
additions are worth making:

1. **Switch to `GHOST_ACCESS_TOKEN`.** Replace `GHOST_TOKEN` (a session token that expires after
   a few months) with `GHOST_ACCESS_TOKEN` (your Ghostfolio security token); the sync then logs
   in at every run. Set only one of the two: both together stop the run with exit 1. See
   [Choose how the sync authenticates](../README.md#1-choose-how-the-sync-authenticates).
2. **Turn on failure alerts** with `APPRISE_URLS` (and optionally `APPRISE_TIMEOUT`). See
   [Failure notifications](../README.md#failure-notifications-apprise).

Then pull the image and **recreate** the container (a restart keeps the old image), run once
with `DRY_RUN=1`, and check the version in the start-up log. The image now also contains Apprise
and its pinned dependencies; the sync never imports them. To roll back to 2.1, set
`GHOST_TOKEN` again first: older images do not understand `GHOST_ACCESS_TOKEN`, and they ignore
`APPRISE_*`.


[Back to the README](../README.md)
