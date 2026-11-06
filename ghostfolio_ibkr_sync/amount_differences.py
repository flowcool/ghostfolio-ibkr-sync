"""Evidence-bound explanations. No cause grants identity or write authority.

Sibling source contracts have no runtime adapter here (ADR 0007). Adding a
cause requires real broker evidence, independent of synthetic test coverage.
"""

from collections.abc import Callable, Sequence
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Literal

from ghostfolio_ibkr_sync.activity_reconciliation import arithmetic_precision
from ghostfolio_ibkr_sync.models import AmountFinding
from ghostfolio_ibkr_sync.sync import _historical_minor_unit

Cause = tuple[str, str, Literal["correct", "information"]]


CauseFunction = Callable[[AmountFinding], Cause | None]


def minor_units(difference: Decimal, currency: str) -> Decimal | None:
    """Absolute units, including fractions. Display rounding is unrelated."""
    unit = _historical_minor_unit(currency)
    if unit is None or not difference.is_finite():
        return None
    with localcontext() as context:
        context.prec = arithmetic_precision(difference, unit)
        return abs(difference) / unit


def declared_rate_rounding(finding: AmountFinding) -> Cause | None:
    """PR200: complete single representation, exact quantity/fee and Re rate."""
    rate, target = finding.declared_rate, finding.destination_gross
    if (finding.broker != "IBKR" or finding.scope != "destination"
            or not finding.complete or finding.associations != 1
            or finding.representations != 1 or finding.components
            or rate is None or not rate.is_finite() or rate <= 0 or target is None
            or finding.destination_quantity != finding.quantity or finding.destination_fee != finding.fee):
        return None
    with localcontext() as context:
        context.prec = arithmetic_precision(finding.quantity, rate, finding.gross, target)
        if (minor_units(target - finding.gross, finding.currency) == 1
                and target == finding.quantity * rate):
            return ("legacy declared-rate rounding",
                    "Legacy row uses the declared rate; IBKR paid a rounded cash amount.", "information")
    return None


def printed_gross_rounding(finding: AmountFinding) -> Cause | None:
    """Pinned BD checked_amounts contract. Source-only, never stored-row tolerance."""
    notice = finding.notice
    if (finding.broker != "BD" or finding.scope != "source" or finding.currency != "EUR"
            or notice is None or not finding.complete or finding.associations != 1
            or any(value is not None for value in (finding.destination_gross,
                finding.destination_fee, finding.destination_quantity))
            or any(not value.is_finite() for value in
                   (notice.price, notice.vat, notice.net, finding.quantity, finding.gross, finding.fee))
            or notice.price <= 0 or finding.gross <= 0 or finding.fee < 0
            or notice.vat != 0 or notice.net <= 0
            or (finding.quantity <= 0 if notice.kind == "BUY" else finding.quantity >= 0)):
        return None
    with localcontext() as context:
        context.prec = arithmetic_precision(finding.quantity, notice.price, finding.gross,
                                            finding.fee, notice.net)
        product = abs(finding.quantity) * notice.price
        difference = minor_units(product - finding.gross, finding.currency)
        net = (finding.gross + finding.fee if notice.kind == "BUY" else finding.gross - finding.fee)
        if (difference is not None and 0 < difference <= Decimal("0.5")
                and product.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == finding.gross
                and net == notice.net):
            return ("printed-gross cent rounding",
                    "Printed gross rounds the exact source price product; fees and net corroborate it.",
                    "information")
    return None


def corroborated_execution_views(finding: AmountFinding) -> Cause | None:
    """Pinned DEGIRO signed-gross contract with complete metadata multiplicities.

    Adapters must supply each API/CSV occurrence, not a deduplicated amount set.
    One occurrence per cash view and one independently associated execution are
    required. This accepts no FX, destination fee or generic rounding policy.
    """
    proof = finding.execution
    if (finding.broker != "DEGIRO" or finding.scope != "source"
            or not finding.complete or finding.associations != 1 or proof is None
            or not proof.cash or proof.product_type != "STOCK"
            or proof.contract_size != 1 or _historical_minor_unit(finding.currency) != Decimal("0.01")
            or any(value is not None for value in (finding.destination_quantity,
                finding.destination_gross, finding.destination_fee))):
        return None
    trade = proof.trade
    identity = (trade.product_id, trade.date, trade.value_date, trade.order_id, trade.currency)
    if (not all(identity) or trade.currency != finding.currency or trade.amount != finding.gross
            or trade.view != "execution" or trade.kind != "EXECUTION"
            or len({row.view for row in proof.cash}) != len(proof.cash)
            or any(row.view not in ("api", "csv") or row.kind != "TRANSACTION"
                   or not row.description.startswith("Achat " if proof.side == "BUY" else "Vente ")
                   for row in proof.cash)
            or any((row.product_id, row.date, row.value_date, row.order_id, row.currency) != identity
                   for row in proof.cash)):
        return None
    amounts = (trade.amount, *(row.amount for row in proof.cash))
    if (any(not value.is_finite() for value in (*amounts, proof.price, finding.quantity))
            or proof.price <= 0 or (finding.quantity <= 0 if proof.side == "BUY" else finding.quantity >= 0)):
        return None
    with localcontext() as context:
        context.prec = arithmetic_precision(amounts, finding.quantity, proof.price)
        gross = -finding.quantity * proof.price
        cent = Decimal("0.01")
        if (0 < max(amounts) - min(amounts) <= cent
                and all(amount % cent == 0 for amount in amounts[1:])
                and all(amount * gross > 0 and abs(amount - gross) <= cent for amount in amounts)):
            return ("corroborated execution views",
                    "Exact signed execution gross corroborates the differing source cash views.", "information")
    return None


# The seven retained observations do not meet the real-data registration gate.
# Synthetic tests and operator-selected profiles cannot replace that evidence.
OMITTED_WITHHOLDING_REAL_PROOF: str | None = None


def omitted_withholding(finding: AmountFinding) -> Cause | None:
    """Candidate only. Keep disabled until retained real one-to-one proof exists."""
    proof = finding.withholding
    if (OMITTED_WITHHOLDING_REAL_PROOF is None or finding.broker != "IBKR"
            or finding.scope != "destination" or not finding.complete or finding.associations != 1
            or proof is None or finding.representations != 1 or finding.components
            or finding.destination_gross != finding.gross
            or finding.destination_quantity != finding.quantity
            or finding.destination_fee != 0 or finding.fee <= 0
            or not proof.payment_amounts or not proof.tax_amounts
            or len(proof.accrual_quantities) != 1 or proof.accrual_quantities[0] != finding.quantity
            or len(proof.action_ids) != len(proof.payment_amounts) + len(proof.tax_amounts) + 1
            or len(set(proof.action_ids)) != 1 or not all(proof.action_ids)
            or any(not amount.is_finite() or amount <= 0 for amount in proof.payment_amounts)
            or any(not amount.is_finite() or amount >= 0 for amount in proof.tax_amounts)):
        return None
    with localcontext() as context:
        context.prec = arithmetic_precision(proof.payment_amounts, proof.tax_amounts, finding.gross, finding.fee)
        if (sum(proof.payment_amounts, Decimal(0)) == finding.gross
                and -sum(proof.tax_amounts, Decimal(0)) == finding.fee):
            return ("omitted withholding", "Complete cash and action evidence proves a missing withholding fee.", "correct")
    return None


CAUSES: tuple[CauseFunction, ...] = (declared_rate_rounding, printed_gross_rounding,
                                   corroborated_execution_views, omitted_withholding)


def classify_amount_difference(finding: AmountFinding,
                              registry: Sequence[CauseFunction] | None = None) -> Cause | None:
    """First qualified match explains its fields. No match leaves review intact."""
    numbers = (finding.quantity, finding.gross, finding.fee, finding.destination_quantity,
               finding.destination_gross, finding.destination_fee)
    if (not finding.complete or finding.associations != 1
            or _historical_minor_unit(finding.currency) is None
            or any(number is not None and not number.is_finite() for number in numbers)):
        return None
    for cause in CAUSES if registry is None else registry:
        result = cause(finding)
        if result is not None:
            return result
    return None
