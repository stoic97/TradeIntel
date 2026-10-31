"""How a figure is written on a page. One place, for every page.

Pages format and never compute (handoff section 8, T7): a figure is decided in
mirror/metrics.py and arrives here as a value; these filters only write it. Registered
on the app's templates once, in app.py.

Rupees are written the Indian way, ₹12,34,567, because that is how Indian brokers and
every trader's own P&L write money; a Western 1,234,567 reads as foreign and is easy
to misread by a factor of ten. A result carries its sign, +₹ or −₹ with the true minus
(U+2212), as the design kit draws it; an amount such as a budget or a price does not.

Every figure is cut to whole units toward zero, exactly as the templates' int() always
cut it, so moving the formatting here changes how a figure is written and never which
figure it is. The tone (loss, gain, plain) follows the figure as printed: a result
printed as ₹0 is not coloured as a loss.
"""

from __future__ import annotations

from decimal import Decimal

MINUS = "\u2212"
RUPEE = "\u20b9"


def _whole(value) -> int:
    """Whole units, cut toward zero. Floats go through str so 0.1 stays 0.1."""
    if isinstance(value, float):
        value = Decimal(str(value))
    return int(value)


def indian_grouping(n: int) -> str:
    """12,34,567: the last three digits, then pairs. The sign is the caller's."""
    digits = str(abs(n))
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while head:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join([*groups, tail])


def rupees(value, signed: bool = True) -> str:
    """−₹12,345 / +₹12,345 / ₹0; with signed=False an amount, ₹12,345, has no plus."""
    n = _whole(value)
    written = RUPEE + indian_grouping(n)
    if n < 0:
        return MINUS + written
    if n > 0 and signed:
        return "+" + written
    return written


def tone(value) -> str:
    """The kit's class suffix for a signed rupee figure: num--loss, num--gain, num--plain."""
    n = _whole(value)
    return "loss" if n < 0 else "gain" if n > 0 else "plain"


def count(value) -> str:
    """A count of trades, days or rows, grouped like money."""
    return indian_grouping(_whole(value))


def minutes(seconds) -> str:
    """Whole minutes from seconds, cut as the templates' (seconds / 60)|int cut them."""
    return count(_whole(Decimal(str(seconds)) / 60))


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def day(iso_date: str) -> str:
    """A trading day as the kit writes it: 2026-09-07 is 07 Sep."""
    _year, month, dom = iso_date.split("-")
    return f"{dom} {MONTHS[int(month) - 1]}"


def register(env) -> None:
    """Make the filters available to every template the app renders."""
    env.filters.update(rupees=rupees, tone=tone, count=count, minutes=minutes, day=day)
