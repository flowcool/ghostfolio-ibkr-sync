"""Immutable records shared across modules; they import nothing from the package."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True, kw_only=True)
class Settings:
    """Validated run settings read from ENV.

    Credentials stay out of repr so a logged or raised object never shows them.
    Exactly one of ghost_token (legacy bearer) or ghost_access_token is set.
    """

    ibkr_token: str = field(repr=False)
    account_ids: tuple[str, ...]
    query_ids: tuple[str, ...]
    account_names: tuple[str, ...]
    ghost_token: str | None = field(repr=False)
    ghost_access_token: str | None = field(repr=False)
    ghost_host: str
    ghost_platform_id: str
    mapping_file: str
    dry_run: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class NotificationSettings:
    """Enabled failure-notification delivery; the URLs carry destination credentials."""

    urls: tuple[str, ...] = field(repr=False)
    timeout: int
