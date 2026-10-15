"""Offline tests for the dividend report coherence check (synthetic report text)."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "check_dividend_report", Path(__file__).parents[1] / "scripts/check_dividend_report.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

PREFIX = "2026-01-02 06:00:00 [INFO] [DRY RUN] "
ROW_A = "aaaaaaaa-0000-4000-8000-000000000001"
ROW_B = "1e661480-0000-4e36-8000-000000000002"  # hex id that looks like E-notation


def wrap(text):
    """Wrap each line like supercronic does in a container log."""
    return "\n".join(
        '2026-01-02T05:00:00.000000000Z time="2026-01-02T06:00:00+01:00" level=info '
        f'msg="{line}" channel=stderr iteration=0 job.command="python /app/ibkr_to_ghostfolio.py"'
        for line in text.splitlines())


def block(header, *body):
    return "\n".join([PREFIX + header + " (account acc-1)"] + [f"  {line}" for line in body])


CLEAN = "\n".join([
    "2026-01-02 06:00:00 [INFO] Found 3 existing dividend activities in Ghostfolio",
    block("Dividend information: total equal to IBKR, split over 2 rows",
          "Security: TEST (ISIN XX0000000001), dividend date 2026-01-01",
          "IBKR: quantity 10, gross 5 USD, fee 0.75 USD",
          f"Ghostfolio: activity {ROW_A} (TEST) on 2026-01-01, quantity 10, gross 2.5 USD, fee 0.75 USD",
          "Action: No action needed.",
          "Proposed match (strong: same security, local day, gross and fee)",
          f"  Keep: activity {ROW_A} (TEST), local day 2026-01-01, quantity 10, gross 2.5 USD",
          f"  Proposed action: No action needed: keep activity {ROW_A}.",
          "Nothing was written."),
    PREFIX + "Dividend report: 1 to check, 1 informational, 0 noise",
    block("Dividend to check: quantity difference",
          f"Ghostfolio: activity {ROW_B} (TEST) on 2026-01-01, quantity 451, gross 2.47 GBP",
          "Currency: IBKR GBP, Ghostfolio GBP (from activity)",
          "Action: Compare the quantity in Ghostfolio with the IBKR statement.",
          f"  Proposed action: Compare activity {ROW_B} with the IBKR statement by hand.",
          "Nothing was written."),
    PREFIX + "Historical dividends account=acc-1 coverage=2 categories=absent:0 failed_checks=none",
    "2026-01-02 06:00:01 [INFO] Sync complete",
])


def rules(text):
    return [rule for rule, _, _ in check.check_report(text)]


def test_clean_report_passes():
    assert check.check_report(CLEAN) == []
    assert check.check_report(wrap(CLEAN)) == []


def test_wrapper_is_stripped_and_lines_are_counted():
    text = wrap(block("Dividend to check: x", "Reason: found None"))
    assert check.check_report(text) == [("repr", 2, "Python literal in report text")]


def test_repr_rule():
    bad = [
        PREFIX + "Historical dividends account=acc-1 categories={'absent': 2} failed_checks={}",
        block("Dividend to check: x", "Identity check isin unavailable: expected XX1, found None"),
        block("Dividend to check: x", "Difference: gross 1.5E-7 USD"),
        block("Dividend to check: x", "Difference: gross Decimal('1.5') USD"),
        block("Dividend to check: x", "Rows: []"),
    ]
    for text in bad:
        assert "repr" in rules(text), text


def test_float_noise_rule():
    assert rules(block("Dividend to check: x", "Ghostfolio: gross 2.470000000000000072 GBP")) == ["float-noise"]
    assert rules(block("Dividend to check: x", "Ghostfolio: gross 0.9999999 GBP")) == ["float-noise"]
    assert rules(block("Dividend to check: x", "Ghostfolio: gross 2.4700013335 GBP")) == []


def test_action_contradiction_rule():
    text = block("Dividend information: total equal to IBKR",
                 "Action: No action needed.",
                 f"  Proposed action: Compare activity {ROW_A} and the other rows by hand.")
    assert rules(text) == ["action-contradiction"]


def test_duplicate_row_same_primary_twice():
    text = "\n".join([
        block("Dividend to check: quantity difference", f"Ghostfolio: activity {ROW_A} (TEST)"),
        block("Dividend to check: probable duplicate", f"Ghostfolio: activity {ROW_A} (TEST)"),
    ])
    assert check.check_report(text) == [
        ("duplicate-row", 4, "same activity is the primary row of the block at line 2")]


def test_duplicate_row_kept_then_absent_source():
    text = "\n".join([
        block("Dividend information: absent source paired with outside-coverage row",
              "Action: No action needed.",
              f"  Keep: activity {ROW_A} (TEST)",
              f"  Proposed action: No action needed: keep activity {ROW_A}."),
        block("Dividend information: outside-coverage row paired with absent source",
              f"Ghostfolio: activity {ROW_A} (TEST)",
              "Action: No action needed."),
    ])
    assert rules(text) == ["duplicate-row"]


def test_currency_rule():
    text = block("Dividend information: unsupported currency",
                 f"Ghostfolio: activity {ROW_A} (TEST), values unavailable",
                 "Reason: missing or unsupported currency context",
                 "Currency: IBKR KRW, Ghostfolio KRW (from activity)")
    assert rules(text) == ["currency"]
    assert rules(text.replace("Ghostfolio KRW", "Ghostfolio USD")) == []


def test_main_exit_codes(tmp_path, capsys):
    clean, bad = tmp_path / "clean.log", tmp_path / "bad.log"
    clean.write_text(wrap(CLEAN), encoding="utf-8")
    bad.write_text(block("Dividend to check: x", "found None"), encoding="utf-8")
    assert check.main(["check", str(clean)]) == 0
    assert check.main(["check", str(bad)]) == 1
    assert capsys.readouterr().out == "repr line 2: Python literal in report text\n"
