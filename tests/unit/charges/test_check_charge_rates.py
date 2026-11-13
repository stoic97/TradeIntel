"""TICKET-911: the stale-rate check prices made-up orders against two brokers' published rates,
alerts a person when they differ or a page can't be read, and never edits the table.

The pages here are small samples in each broker's own layout, with today's rates. No network.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from services.production.charges import rates as R

_spec = importlib.util.spec_from_file_location("check_charge_rates", Path("scripts/check_charge_rates.py"))
K = importlib.util.module_from_spec(_spec)
sys.modules["check_charge_rates"] = K
_spec.loader.exec_module(K)
S, C = R.Segment, R.Component
TODAY = date(2026, 11, 13)

FYERS = """### Equity

| CHARGES | DELIVERY | INTRADAY | FUTURES | OPTIONS |
| --- | --- | --- | --- | --- |
| STT/CTT | 0.1% on Buy and Sell value | 0.025% on Sell value | 0.05% on Sell value | 0.15% on Sell value (Premium) on option exercised |
| Exchange Transaction Charges | NSE: 0.0030699% | NSE: 0.0030699% | NSE: 0.0018299% | NSE: 0.0355299% (On premium) |
|  | BSE: 0.00375% | BSE: 0.00375% |  | BSE Sensex: 0.0325% Bankex: 0.0325% Sensex 50: 0.005% Stock: 0.005% |
| SEBI Turnover Fee | ₹10/Crore | ₹10/Crore | ₹10/Crore | ₹10/Crore |
| GST | 18% on (Brokerage + Exchange Transaction charges + SEBI Turnover Fee + NSE IPFT) | 18% on x | 18% on x | 18% on x |
| Stamp Duty | 0.015% on buy value | 0.003% on buy value | 0.002% on buy value | 0.003% on buy value |
| NSE IPFT | ₹0.01/Crore | ₹0.01/Crore | ₹0.01/Crore | ₹0.01/Crore (On Premium) |

### Commodity

| CHARGES | FUTURES | OPTIONS |
| --- | --- | --- |
| STT/CTT | 0.01% on sell side (Non-Agri) | 0.05% on sell side |
| Exchange Transaction Charges | MCX- Non-Agri: 0.0021% | MCX- Non-Agri: 0.0418% |
|  | NSE- 0.0001% | NSE- 0.001% |
| SEBI Turnover Fee | Non-Agri: ₹10/Crore + GST | Non-Agri: ₹10/Crore + GST |
| GST | 18% on (Brokerage + x) | 18% on (Brokerage + x) |
| Stamp Duty | 0.002% on Buy Side | 0.003% on Buy Side |

## Other charges
"""


def zerodha(fo_options="0.03553"):
    """Zerodha's layout: one equity and F&O table (delivery, intraday, futures, options), an old
    F&O table left inside an HTML comment, then commodity."""
    cells = [
        "Equity", "Equity delivery", "Equity intraday", "F&O - Futures", "F&O - Options", "Brokerage",
        "Zero Brokerage", "0.03%", "0.03%", "Flat Rs. 20",
        "STT/CTT", "0.1% on buy & sell", "0.025% on the sell side", "0.05% on the sell side",
        "0.15% of the intrinsic value on options that are bought and exercised", "0.15% on sell side (on premium)",
        "Transaction charges", "NSE: 0.00307%", "BSE: 0.00375%", "NSE: 0.00307%", "BSE: 0.00375%",
        "NSE: 0.00183%", "BSE: 0", f"NSE: {fo_options}% (on premium)", "BSE: 0.0325% (on premium)",
        "GST", "18% on (brokerage + SEBI charges + transaction charges)",
        "SEBI charges", "₹10 / crore", "₹10 / crore", "₹10 / crore", "₹10 / crore",
        "Stamp charges", "0.015% or ₹1500 / crore on buy side", "0.003% or ₹300 / crore on buy side",
        "0.002% or ₹200 / crore on buy side", "0.003% or ₹300 / crore on buy side",
    ]
    old = "<!-- <td>F&O - Futures</td><td>F&O - Options</td><td>Brokerage</td><td>NSE: 9.9%</td> -->"
    commodity = [
        "Commodity", "Commodity futures", "Commodity options", "Brokerage", "0.03%", "₹ 20",
        "STT/CTT", "0.01% on sell side (Non-Agri)", "0.05% on sell side",
        "Transaction charges", "MCX: 0.0021%", "NSE: 0.0001%", "MCX: 0.0418%", "NSE: 0.001%",
        "GST", "18% on x", "SEBI charges", "Non-agri:", "₹10 / crore", "₹10 / crore",
        "Stamp charges", "0.002% or ₹200 / crore on buy side", "0.003% or ₹300 / crore on buy side",
        "US Equity",
    ]
    cell = lambda cs: "".join(f"<td>{c}</td>" for c in cs)
    return f"<table>{cell(cells)}{old}{cell(commodity)}</table>"


def test_fyers_page_is_read_into_the_tables_keys():
    got = K.fyers_rates(FYERS)
    assert got[(S.NSE_OPT, C.STT, "sell")] == Decimal("0.0015")
    assert got[(S.NSE_OPT, C.EXCHANGE, "buy")] == Decimal("0.000355299")
    assert got[(S.NSE_OPT, C.IPFT, "buy")] == Decimal("0.000000001")
    assert got[(S.MCX_OPT, C.EXCHANGE, "sell")] == Decimal("0.000418")
    assert got[(S.BSE_OPT, C.EXCHANGE, "sell")] == Decimal("0.000325")


def test_zerodha_page_is_read_into_the_tables_keys():
    got = K.zerodha_rates(zerodha())
    assert got[(S.NSE_FUT, C.STT, "sell")] == Decimal("0.0005")
    assert got[(S.NSE_OPT, C.EXCHANGE, "sell")] == Decimal("0.0003553")
    assert got[(S.NSE_FUT, C.STAMP, "buy")] == Decimal("0.00002")
    assert got[(S.MCX_FUT, C.CTT, "sell")] == Decimal("0.0001")


def test_todays_table_matches_both_samples_on_every_made_up_order():
    assert K.compare(K.fyers_rates(FYERS), TODAY) == []
    assert K.compare(K.zerodha_rates(zerodha()), TODAY) == []


def test_a_rate_that_moved_on_the_page_is_an_alert_naming_the_order():
    found = K.compare(K.zerodha_rates(zerodha(fo_options="0.04")), TODAY)
    assert found and all("NSE_OPT" in line and "EXCHANGE" in line for line in found)


def test_an_unreadable_page_is_itself_an_alert():
    pages = {K.FYERS: "nothing like the page", K.ZERODHA: zerodha()}
    alerts = K.run(TODAY, fetch=lambda url: pages[url])
    assert len(alerts) == 1 and alerts[0].startswith("FYERS: couldn't read")


def test_the_job_never_writes_the_table():
    before = (R.TABLE.read_bytes(), R.LOCK.read_bytes())
    pages = {K.FYERS: FYERS, K.ZERODHA: zerodha(fo_options="0.04")}
    assert K.run(TODAY, fetch=lambda url: pages[url])
    assert (R.TABLE.read_bytes(), R.LOCK.read_bytes()) == before


def test_only_made_up_orders_are_priced():
    assert len(K.ORDERS) == 14 and {seg for seg, _, _ in K.ORDERS} <= set(R.REQUIRED)
