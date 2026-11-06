"""Immutable records shared across modules; they import nothing from the package."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True, slots=True)
class DividendContext:
    """Known security/day context; None cannot rule out an overlapping event."""

    symbol: str | None
    isin: str | None
    day: str | None


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
    activity_review_file: str | None = None
    activity_reconciliation: str = "off"
    corporate_action_state_file: str | None = None
    corporate_action_evidence_file: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class NotificationSettings:
    """Enabled failure-notification delivery; the URLs carry destination credentials."""

    urls: tuple[str, ...] = field(repr=False)
    timeout: int


@dataclass(frozen=True)
class PrintedGross:
    kind: Literal["BUY", "SELL"]
    price: Decimal
    vat: Decimal
    net: Decimal


@dataclass(frozen=True)
class ExecutionView:
    product_id: str
    date: str
    value_date: str
    order_id: str
    currency: str
    amount: Decimal
    view: Literal["execution", "api", "csv"]
    kind: str
    description: str


@dataclass(frozen=True)
class ExecutionViews:
    side: Literal["BUY", "SELL"]
    product_type: str
    contract_size: Decimal
    price: Decimal
    trade: ExecutionView
    cash: tuple[ExecutionView, ...]


@dataclass(frozen=True)
class WithholdingEvidence:
    payment_amounts: tuple[Decimal, ...]
    tax_amounts: tuple[Decimal, ...]
    action_ids: tuple[str, ...]
    accrual_quantities: tuple[Decimal, ...]


@dataclass(frozen=True)
class AmountFinding:
    broker: str
    currency: str
    scope: Literal["source", "destination"]
    complete: bool
    associations: int
    quantity: Decimal
    gross: Decimal
    fee: Decimal
    destination_quantity: Decimal | None = None
    destination_gross: Decimal | None = None
    destination_fee: Decimal | None = None
    declared_rate: Decimal | None = None
    representations: int = 0
    components: int = 0
    notice: PrintedGross | None = None
    execution: ExecutionViews | None = None
    withholding: WithholdingEvidence | None = None
