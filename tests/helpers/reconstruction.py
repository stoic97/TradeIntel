"""Moved out of tests/unit/test_reconstruction.py by TICKET-945, so that no test file imports another.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from services.shared.schemas.ctr_v1 import Fill, OptionType, Segment

IST = datetime(2026, 9, 1, 9, 15, 0).astimezone().tzinfo


T0 = datetime(2026, 9, 1, 9, 15, 0, tzinfo=IST)


RAW = "c" * 64


CRUDE = {
    "exchange": "MCX",
    "segment": Segment.OPT,
    "symbol": "CRUDEOILM",
    "expiry": date(2026, 9, 17),
    "option_type": OptionType.CE,
    "strike": Decimal(5500),
}


def fill(side, qty, price, minutes=0, **contract):
    return Fill(
        trader_id="T01",
        broker="dhan",
        ts=T0 + timedelta(minutes=minutes),
        side=side,
        quantity=qty,
        price=Decimal(str(price)),
        raw_hash=RAW,
        **(contract or CRUDE),
    )
