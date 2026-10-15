#!/usr/bin/env python3
"""Check the dividend report of a connector log for coherence defects.

Usage: check_dividend_report.py [LOG_FILE]   (reads stdin when no file is given)

Reads a container log (supercronic wrapper lines are unwrapped) or plain
connector output, splits the dividend report into blocks and prints one
violation per line: "<rule> line <n>: <reason>". Reasons never repeat amounts
or activity ids. Exit status: 1 on any violation, 0 otherwise.

Rules:
  repr                  Python literal in the report (dict, list, None, Decimal(),
                        E-notation number)
  float-noise           a run of 6+ zeros or 6+ nines after a decimal point
  action-contradiction  "Action: No action needed." with a proposed action that
                        asks for manual work
  duplicate-row         one Ghostfolio activity is the primary row of two blocks,
                        or is kept in one block and primary of an absent-source /
                        outside-coverage block
  currency              "unsupported currency" reason while both sides show the
                        same known currency code
"""

import re
import sys

WRAPPER = re.compile(r'^(?:\S+Z\s+)?time="[^"]*"\s+level=\w+\s+msg="((?:[^"\\]|\\.)*)"')
BLOCK_HEADER = re.compile(r"\[(?:INFO|DEBUG|WARNING)\] (?:\[DRY RUN\] )?Dividend "
                          r"(?:to check|information|noise|coherent|outside report window): ")
SUMMARY = re.compile(r"\[DRY RUN\] (?:Dividend report:|Historical dividends )")
REPR = re.compile(r"\{['\"]|\[['\"{]|\[\]|\{\}|\bNone\b|Decimal\(|"
                  r"(?<![\w.#-])\d+(?:\.\d+)?[eE][+-]?\d+(?![\w.#-])")
FLOAT_NOISE = re.compile(r"\d\.\d*(?:0{6,}|9{6,})")
PRIMARY = re.compile(r"^Ghostfolio: activity (\S+)")
KEEP = re.compile(r"^Keep: activity (\S+)")
CURRENCY = re.compile(r"^Currency: IBKR ([A-Z]{3}), Ghostfolio ([A-Z]{3})\b")
UNSUPPORTED = "missing or unsupported currency context"


def unwrap(raw):
    """Return the message of a supercronic wrapper line, or the line itself."""
    match = WRAPPER.match(raw)
    if not match:
        return raw
    return re.sub(r"\\(.)", r"\1", match.group(1))


def report_lines(text):
    """Return [(line_number, message)] for every input line, 1-based."""
    return [(number, unwrap(raw)) for number, raw in enumerate(text.splitlines(), 1)]


def split_blocks(lines):
    """Return (blocks, summaries): blocks are lists of (n, msg) starting at a header."""
    blocks, summaries, current = [], [], None
    for number, message in lines:
        if BLOCK_HEADER.search(message):
            current = [(number, message)]
            blocks.append(current)
        elif current is not None and message[:1].isspace():
            current.append((number, message))
        else:
            current = None
            if SUMMARY.search(message):
                summaries.append((number, message))
    return blocks, summaries


def check_literals(lines):
    """Rules repr and float-noise on every report line."""
    violations = []
    for number, message in lines:
        if REPR.search(message):
            violations.append(("repr", number, "Python literal in report text"))
        if FLOAT_NOISE.search(message):
            violations.append(("float-noise", number, "floating-point noise in a number"))
    return violations


def check_action(block):
    """Rule action-contradiction for one block."""
    no_action = any(message.strip().startswith("Action: No action needed") for _, message in block)
    if not no_action:
        return []
    violations = []
    for number, message in block:
        text = message.strip()
        if text.startswith("Proposed action:") and \
                not text[len("Proposed action:"):].strip().startswith("No action needed"):
            violations.append(("action-contradiction", number,
                               "block says no action needed but proposes manual work"))
    return violations


def check_currency(block):
    """Rule currency for one block."""
    unsupported = any(message.strip().startswith("Reason:") and UNSUPPORTED in message
                      for _, message in block)
    if not unsupported:
        return []
    violations = []
    for number, message in block:
        match = CURRENCY.match(message.strip())
        if match and match.group(1) == match.group(2):
            violations.append(("currency", number,
                               "unsupported currency reason while both sides show the same code"))
    return violations


def primary_row(block):
    """Return (line_number, activity_id) of the block's first Ghostfolio row, or None."""
    for number, message in block[1:]:
        match = PRIMARY.match(message.strip())
        if match:
            return number, match.group(1)
    return None


def check_duplicates(blocks):
    """Rule duplicate-row across blocks."""
    violations, seen, kept = [], {}, {}
    for block in blocks:
        for number, message in block:
            match = KEEP.match(message.strip())
            if match:
                kept.setdefault(match.group(1), number)
    for block in blocks:
        primary = primary_row(block)
        if primary is None:
            continue
        number, activity = primary
        if activity in seen:
            violations.append(("duplicate-row", number,
                               f"same activity is the primary row of the block at line {seen[activity]}"))
        else:
            seen[activity] = number
        header = block[0][1]
        if ("absent source" in header or "outside-coverage" in header) and activity in kept:
            violations.append(("duplicate-row", number,
                               f"absent/outside-coverage row is kept in the block at line {kept[activity]}"))
    return violations


def check_report(text):
    """Return the sorted violations [(rule, line_number, reason)] of a log text."""
    blocks, summaries = split_blocks(report_lines(text))
    violations = check_literals(summaries + [line for block in blocks for line in block])
    for block in blocks:
        violations += check_action(block) + check_currency(block)
    violations += check_duplicates(blocks)
    return sorted(violations, key=lambda item: (item[1], item[0]))


def main(argv):
    if len(argv) > 2:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    if len(argv) == 2:
        with open(argv[1], encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    else:
        text = sys.stdin.read()
    violations = check_report(text)
    for rule, number, reason in violations:
        print(f"{rule} line {number}: {reason}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
