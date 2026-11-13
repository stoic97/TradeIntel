"""TICKET-911: has the statutory rate table gone stale? A job, separate from the product.

    uv run python scripts/check_charge_rates.py [--webhook URL]

It prices a fixed set of made-up orders twice for today: once with the table
(services/production/charges/rates.yaml), and once with the rates two brokers publish
(FYERS's charges list and Zerodha's charges page). If any component differs by more than a
paisa, or a page can't be read, it prints what moved, posts it to the webhook if one is given
(or set in SCOPE_ALERT_WEBHOOK), and exits 1. A person then reads the circular and adds a
row. **The job never edits the table**: an automatic update would silently rewrite history.

Made-up orders only. No trader's trade is ever read here.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.production.charges import rates as R

S, C = R.Segment, R.Component
FYERS = "https://fyers.in/charges-list.md"
ZERODHA = "https://zerodha.com/charges"
CRORE = Decimal(10_000_000)
TOLERANCE = Decimal("0.01")  # a paisa

ORDERS: tuple = ()


def fyers_rates(text):
    raise NotImplementedError


def zerodha_rates(page):
    raise NotImplementedError


def compare(published, on):
    raise NotImplementedError


def run(on, fetch=None):
    raise NotImplementedError
