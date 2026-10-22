"""Shared synthetic sync inputs and isolated HTTP doubles for offline tests."""
import json
import xml.etree.ElementTree as ET
from collections import defaultdict

import requests

from ghostfolio_ibkr_sync import app, diagnostics, ghostfolio, ibkr


ISIN_KO = "US1912161007"
ISIN_PEP = "US7134481081"
ACC = "gf-acc"
CFG = {"ibkr_token": "SECRET-TOK", "dry_run": False, "ghost_host": "http://g", "ghost_token": "t"}


def positions(qty=None, versioned_identities=None):
    return {"qty": defaultdict(float, qty or {}), "isin_symbols": defaultdict(set),
            "manual_sells": defaultdict(list), "manual_buys": defaultdict(list),
            "dividend_dates": defaultdict(list),
            "versioned_identities": set(versioned_identities or ())}


def trade_xml(tid, side="BUY", qty=10, symbol="KO", isin=ISIN_KO, date="20260801;100000", **extra):
    q = qty if side == "BUY" else -qty
    attrs = {"tradeID": tid, "symbol": symbol, "isin": isin, "assetCategory": "STK", "buySell": side,
             "quantity": q, "tradePrice": 60, "ibCommission": -1, "currency": "USD", "dateTime": date}
    attrs.update(extra)
    return "<Trade " + " ".join(f'{k}="{v}"' for k, v in attrs.items()) + "/>"


def flex_datetime(date):
    """Cash rows carry the mandatory Flex form YYYYMMDD;HHmmss TimeZone."""
    return date if ";" in date else f"{date};120000 EST"


def div_xml(amount="25.00", date="20260715", isin=ISIN_KO, symbol="KO"):
    date = flex_datetime(date)
    return (f'<CashTransaction type="Dividends" levelOfDetail="DETAIL" amount="{amount}" dateTime="{date}" '
            'accountId="broker-account" conid="1" actionID="A1" exDate="20260701" '
            f'isin="{isin}" symbol="{symbol}" currency="USD" description="X CASH DIVIDEND USD 0.25 PER SHARE"/>')


def report(trades="", divs="", cash="100.5", cash_section=True, base_currency="USD",
           source_account="U1"):
    cash_xml = (f'<CashReport><CashReportCurrency currency="BASE_SUMMARY" endingCash="{cash}"/></CashReport>'
                if cash is not None else "")
    info = f'<AccountInformation accountId="{source_account}" currency="{base_currency}"/>' if base_currency else ""
    parsed_trades = ET.fromstring(f"<R>{trades}</R>")
    for row in parsed_trades:
        if "accountId" not in row.attrib:
            row.set("accountId", source_account)
    trades = "".join(ET.tostring(row, encoding="unicode") for row in parsed_trades)
    divs = divs.replace('accountId="broker-account"', f'accountId="{source_account}"')
    ct = f"<CashTransactions>{divs}</CashTransactions>" if cash_section else ""
    # Enrich existing fixtures; input compatibility scenarios belong to task 2.1.
    accruals = []
    for row in ET.fromstring(f"<R>{divs}</R>"):
        if row.get("type") != "Dividends":
            continue
        attrs = {key: row.get(key, "") for key in ("accountId", "conid", "currency", "actionID", "exDate")}
        attrs.update(quantity="100", code="Re", payDate=row.get("dateTime", "")[:8],
                     date=row.get("dateTime", "")[:8], reportDate=row.get("dateTime", "")[:8])
        accruals.append(ET.tostring(ET.Element("ChangeInDividendAccrual", attrs), encoding="unicode"))
    evidence = "<ChangeInDividendAccruals>" + "".join(accruals) + "</ChangeInDividendAccruals>"
    return (f"<FlexQueryResponse><FlexStatements><FlexStatement>{info}<Trades>{trades}</Trades>{ct}{cash_xml}{evidence}"
            f"</FlexStatement></FlexStatements></FlexQueryResponse>")


class World:
    """Records every side effect so tests can assert on what process_account did."""
    def __init__(self, monkeypatch, xml, find=ACC, import_ok=True, cash_ok=True):
        self.imported, self.cash_calls = [], []
        self.import_ok, self.cash_ok = import_ok, cash_ok
        monkeypatch.setattr(app, "fetch_flex_report", self._fetch(xml))
        monkeypatch.setattr(app, "ghost_find_account_id", self._find(find))
        monkeypatch.setattr(app, "ghost_import_activities", self._import)
        monkeypatch.setattr(app, "ghost_update_cash_balance", self._cash)

    @staticmethod
    def _fetch(xml):
        def f(*a, **k):
            if isinstance(xml, Exception):
                raise xml
            return xml
        return f

    @staticmethod
    def _find(result):
        def f(*a):
            if isinstance(result, Exception):
                raise result
            return result
        return f

    def _import(self, cfg, acts):
        self.imported.append(list(acts))
        return (list(acts), True) if self.import_ok else ([], False)

    def _cash(self, cfg, acc, balance, base_currency):
        if isinstance(self.cash_ok, Exception):
            raise self.cash_ok
        self.cash_calls.append((acc, balance))
        return self.cash_ok

    def run(self, ids=None, comments=None, pos=None, mapping=None, source_account="U1"):
        self.ids = set() if ids is None else ids
        self.comments = set() if comments is None else comments
        self.pos = pos or positions()
        self.result = app.process_account(
            CFG, source_account, "q1", "IBKR", mapping or {},
            self.ids, self.comments, self.pos,
        )
        return self.result

    @property
    def activities(self):
        return [a for batch in self.imported for a in batch]


def structured_input_xml(mode="valid", field="quantity"):
    root = ET.fromstring(report(trade_xml("INPUT-T"),
                                div_xml() + div_xml(isin=ISIN_PEP, symbol="PEP")))
    section = root.find(".//ChangeInDividendAccruals")
    # Distinct securities must have distinct broker contract/action identities.
    root.findall(".//CashTransaction")[1].set("conid", "2")
    section[1].set("conid", "2")
    root.findall(".//CashTransaction")[1].set("actionID", "A2")
    section[1].set("actionID", "A2")
    first = section[0]
    if mode == "old":
        root.find(".//FlexStatement").remove(section)
    elif mode == "empty":
        section.clear()
    elif mode == "missing":
        del first.attrib[field]
    elif mode == "blank":
        first.set(field, "")
    elif mode == "payment_missing":
        del root.find(".//CashTransaction").attrib[field]
    elif mode == "payment_blank":
        root.find(".//CashTransaction").set(field, "")
    elif mode == "conflict":
        row = ET.SubElement(section, "ChangeInDividendAccrual", dict(first.attrib))
        row.set("code", "Po")
        row.set("quantity", "99")
    elif mode == "short":
        first.set("date", "20260701")
        first.set("reportDate", "20260701")
    elif mode == "unrelated":
        ET.SubElement(section, "ChangeInDividendAccrual", {field: "unrelated"})
        ET.SubElement(root.find(".//CashTransactions"), "CashTransaction", {
            "type": "Other Fees", "amount": "bad"})
    return ET.tostring(root, encoding="unicode")


def destination(**changes):
    row = {"id": "dividend-1", "type": "DIVIDEND", "accountId": ACC,
           "comment": f"dividend#{ISIN_KO}#2026-07-15", "date": "2026-07-15T00:00:00Z",
           "quantity": 100, "unitPrice": 0.25, "fee": 0, "currency": "USD",
           "assetProfile": {"symbol": "KO", "isin": ISIN_KO, "dataSource": "YAHOO", "currency": "USD"}}
    row.update(changes)
    return row


def read(monkeypatch, rows, wire=None, dry=True):
    response = requests.Response()
    response.status_code = 200
    response._content = (wire or json.dumps({"activities": rows, "count": len(rows)})).encode()
    calls = []
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: calls.append((args, kwargs)) or response)
    result = ghostfolio.ghost_get_existing_orders({**CFG, "dry_run": dry})
    assert len(calls) == 1
    return result


def comparison(monkeypatch, rows, xml=None, wire=None):
    _, _, positions = read(monkeypatch, rows, wire)
    source = ibkr.parse_cash_dividends(xml or report(divs=div_xml()))
    return diagnostics.historical_dividend_comparison(source, ACC, {}, positions)
