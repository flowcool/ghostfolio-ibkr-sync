"""Sanitized source shapes. Synthetic examples do not qualify a new cause."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from ghostfolio_ibkr_sync import amount_differences as causes
from ghostfolio_ibkr_sync import models


def declared(**changes):
    return replace(models.AmountFinding(
        broker="IBKR", currency="JPY", scope="destination", complete=True,
        associations=1, quantity=D("100"), gross=D("2541"), fee=D("0"),
        destination_quantity=D("100"), destination_gross=D("2540"),
        destination_fee=D("0"), declared_rate=D("25.4"),
        representations=1, components=0), **changes)


def test_registry_declared_rate_and_absolute_fractional_minor_units():
    assert causes.classify_amount_difference(declared()) == (
        "legacy declared-rate rounding",
        "Legacy row uses the declared rate; IBKR paid a rounded cash amount.", "information")
    assert causes.minor_units(D("0.005"), "EUR") == D("0.5")
    assert causes.minor_units(D("-1"), "JPY") == D("1")
    assert causes.minor_units(D("0.001"), "UNKNOWN") is None


@pytest.mark.parametrize("change", [
    {"broker": "BD"}, {"currency": "UNKNOWN"}, {"complete": False},
    {"associations": 2}, {"representations": 2}, {"components": 1},
    {"declared_rate": None}, {"destination_fee": D("1")},
    {"destination_quantity": D("99.999")}, {"destination_gross": D("2539")},
    {"quantity": D("NaN")}, {"scope": "source"},
])
def test_registry_refuses_missing_or_conflicting_evidence(change):
    assert causes.classify_amount_difference(declared(**change)) is None


def test_registry_first_match_wins():
    def first(finding):
        return ("first", "gross only", "information")
    def later(finding):
        return ("later", "fee", "correct")
    assert causes.classify_amount_difference(declared(), (first, later))[0] == "first"
    assert causes.classify_amount_difference(declared(), ()) is None


def printed(**changes):
    return replace(models.AmountFinding(
        broker="BD", currency="EUR", scope="source", complete=True, associations=1,
        quantity=D("3"), gross=D("1.01"), fee=D("0.10"),
        notice=models.PrintedGross(kind="BUY", price=D("0.335"), vat=D("0"), net=D("1.11"))), **changes)


def test_cause_catalogue_printed_gross_half_cent_tie_and_sell():
    assert causes.classify_amount_difference(printed())[2] == "information"
    sell = printed(quantity=D("-3"), notice=models.PrintedGross(
        kind="SELL", price=D("0.335"), vat=D("0"), net=D("0.91")))
    assert causes.classify_amount_difference(sell)[0] == "printed-gross cent rounding"


@pytest.mark.parametrize("change", [
    {"broker": "IBKR"}, {"currency": "USD"}, {"scope": "destination"},
    {"destination_fee": D("0")}, {"gross": D("1.02")}, {"fee": D("0.11")},
    {"quantity": D("-3")}, {"complete": False}, {"associations": 2},
    {"notice": models.PrintedGross(kind="BUY", price=D("0.335"), vat=D("0.01"), net=D("1.12"))},
    {"notice": models.PrintedGross(kind="BUY", price=D("0.335"), vat=D("0"), net=D("1.10"))},
])
def test_cause_catalogue_printed_gross_never_excuses_other_fields(change):
    assert causes.classify_amount_difference(printed(**change)) is None


def execution(**changes):
    trade = models.ExecutionView("product", "2026-08-01T10:00:00Z", "2026-08-03", "order", "EUR", D("10.00"),
                                 "execution", "EXECUTION", "Vente synthetic")
    cash = replace(trade, amount=D("10.01"), view="api", kind="TRANSACTION")
    proof = models.ExecutionViews("SELL", "STOCK", D("1"), D("0.3335"), trade, (cash,))
    return replace(models.AmountFinding(
        broker="DEGIRO", currency="EUR", scope="source", complete=True, associations=1,
        quantity=D("-30"), gross=D("10.00"), fee=D("0"), execution=proof), **changes)


def test_cause_catalogue_execution_views_are_independently_corroborated():
    finding = execution()
    assert causes.classify_amount_difference(finding) == (
        "corroborated execution views",
        "Exact signed execution gross corroborates the differing source cash views.", "information")
    assert causes.minor_units(D("10.005") - finding.gross, "EUR") == D("0.5")


@pytest.mark.parametrize("field,value", [
    ("product_type", "OPTION"), ("contract_size", D("100")), ("price", D("0.34")),
    ("side", "BUY"), ("cash", ()),
])
def test_cause_catalogue_execution_view_product_and_sign_guards(field, value):
    finding = execution()
    assert causes.classify_amount_difference(replace(finding, execution=replace(finding.execution, **{field: value}))) is None


@pytest.mark.parametrize("field,value", [
    ("product_id", "other"), ("date", "2026-08-01T10:00:01Z"),
    ("value_date", "2026-08-04"), ("order_id", "other"), ("currency", "USD"),
    ("amount", D("10.02")), ("amount", D("10.005")), ("amount", D("-10.01")),
    ("kind", "FEE"), ("description", "Achat synthetic"), ("view", "execution"),
])
def test_cause_catalogue_execution_view_metadata_and_cash_guards(field, value):
    finding = execution()
    proof = finding.execution
    cash = replace(proof.cash[0], **{field: value})
    assert causes.classify_amount_difference(replace(finding, execution=replace(proof, cash=(cash,)))) is None


@pytest.mark.parametrize("change", [
    {"currency": "JPY"}, {"broker": "IBKR"}, {"scope": "destination"},
    {"associations": 2}, {"destination_fee": D("1")}, {"complete": False},
])
def test_cause_catalogue_execution_views_do_not_excuse_destination_differences(change):
    assert causes.classify_amount_difference(execution(**change)) is None


def test_cause_catalogue_execution_views_preserve_row_multiplicity():
    finding = execution()
    proof = finding.execution
    assert causes.classify_amount_difference(replace(finding, execution=replace(proof, cash=proof.cash * 2))) is None


def omission(**changes):
    return declared(currency="USD", gross=D("25"), fee=D("3"),
        destination_gross=D("25"), destination_fee=D("0"), declared_rate=None,
        withholding=models.WithholdingEvidence(
            payment_amounts=(D("25"),), tax_amounts=(D("-3"),),
            action_ids=("A1", "A1", "A1"), accrual_quantities=(D("100"),)), **changes)


def test_manual_entry_real_data_gate_is_closed_even_for_complete_synthetic_proof(monkeypatch):
    assert causes.classify_amount_difference(omission()) is None
    # This exercises a predicate, not real-data qualification or write authority.
    monkeypatch.setattr(causes, "OMITTED_WITHHOLDING_REAL_PROOF", "synthetic-predicate-test-only")
    assert causes.classify_amount_difference(omission()) == (
        "omitted withholding", "Complete cash and action evidence proves a missing withholding fee.", "correct")


@pytest.mark.parametrize("change", [
    {"complete": False}, {"associations": 2}, {"destination_gross": None},
    {"destination_gross": D("24.99")}, {"destination_quantity": D("99")},
    {"destination_fee": D("1")}, {"fee": D("2")}, {"broker": "BD"},
    {"withholding": models.WithholdingEvidence((D("25"),), (D("-4"), D("1")), ("A1",) * 4, (D("100"),))},
    {"withholding": models.WithholdingEvidence((D("25"),), (D("-3"),), ("A1", "A2", "A1"), (D("100"),))},
    {"withholding": None},
])
def test_manual_entry_omission_needs_exact_complete_independent_proof(monkeypatch, change):
    monkeypatch.setattr(causes, "OMITTED_WITHHOLDING_REAL_PROOF", "synthetic-predicate-test-only")
    assert causes.classify_amount_difference(replace(omission(), **change)) is None
