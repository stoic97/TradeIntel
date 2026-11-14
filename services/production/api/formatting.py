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

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from services.production.api.figures import Figure, through_figure

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


def rupees(value, signed: bool = True, exact: bool = False) -> str:
    """−₹12,345 / +₹12,345 / ₹0; with signed=False an amount, ₹12,345, has no plus.

    exact=True keeps the paise metrics decided (an average, −₹911.76) rather than
    cutting to whole rupees: a figure with paise is a different figure without them.
    """
    n = _whole(value)
    written = RUPEE + indian_grouping(n)
    if exact:
        fraction = str(abs(Decimal(str(value)))).partition(".")[2]
        written += f".{fraction}" if fraction else ""
        if n == 0 and Decimal(str(value)) < 0:
            return MINUS + written
    if n < 0:
        return MINUS + written
    if n > 0 and signed:
        return "+" + written
    return written


def rupees_on_a_trade(value) -> str:
    """As rupees, but a real amount under a rupee keeps its paise.

    On one trade, a win of 96 paise cut to ₹0 reads as a winner that made nothing. Totals
    and averages keep the whole-rupee cut.
    """
    paise = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if _whole(value) != 0 or not paise:
        return rupees(value)
    return f"{MINUS if paise < 0 else '+'}{RUPEE}{abs(paise)}"


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


def minutes_seconds(seconds: int) -> str:
    """A gap between two trades: 1:30, 0:12. Minutes are not carried into hours."""
    whole_minutes, rest = divmod(int(seconds), 60)
    return f"{whole_minutes}:{rest:02d}"


SECONDS_A_DAY = 24 * 60 * 60
DAYS_A_MONTH = 30


def _units(n: int, unit: str) -> str:
    return f"{count(n)} {unit}{'' if n == 1 else 's'}"


def hold(seconds) -> str:
    """How long a position was open, the one way every page writes it (TICKET-818).

    Under a day it is whole minutes, as a day trader counts them: 375 min. From a day it is
    days, and from 30 days months and days: 29 days, 1 month, 13 months 10 days. A month is
    30 days, so the same seconds read the same whichever dates they fell on, and each unit
    is cut down as every figure here is: a hold of 1 day 23 hours is 1 day.
    """
    whole_days = _whole(Decimal(str(seconds)) / SECONDS_A_DAY)
    if whole_days < 1:
        return f"{minutes(seconds)} min"
    months, days = divmod(whole_days, DAYS_A_MONTH)
    parts = ([_units(months, "month")] if months else []) + ([_units(days, "day")] if days else [])
    return " ".join(parts)


def lots(value) -> str:
    """Average lots to one decimal, as the Journal says them: 1.7, not 1.667."""
    return str(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def price(value) -> str:
    """A traded price with its paise, as the broker's file writes it: 2,345.50. Not rupees
    with a sign: a price is an amount, and the paise are the point of it."""
    cut = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole, _, paise = f"{abs(cut):f}".partition(".")
    return f"{indian_grouping(int(whole))}.{paise}"


def out_of_a_hundred(rate) -> str:
    """A rate as a count: 45.8 is "46 of 100". Rounded as a person says it, half up."""
    return f"{Decimal(str(rate)).quantize(Decimal(1), rounding=ROUND_HALF_UP)} of 100"


def signed_percent(value) -> str:
    """A result against what was paid, to one decimal, signed as a result is: +3.9%, −4.5%."""
    cut = Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if not cut:
        return "0.0%"
    return f"{MINUS if cut < 0 else '+'}{abs(cut)}%"


def time_of_day(when) -> str:
    """A clock time as a sentence says it: 9:17 am, 2:51 pm, 12:05 pm."""
    return f"{when.hour % 12 or 12}:{when.minute:02d} {'am' if when.hour < 12 else 'pm'}"


def minutes_in_words(seconds: int, *, about: bool = True) -> str:
    """A hold in a sentence, to the nearest minute: about 3 minutes. Never about 0 minutes."""
    if seconds < 30:
        return "under a minute"
    whole = (seconds + 30) // 60
    words = f"{count(whole)} {'minute' if whole == 1 else 'minutes'}"
    return f"about {words}" if about else words


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def day(iso_date: str) -> str:
    """A trading day with its year, 2026-09-07 is 07 Sep 2026. The kit writes 07 Sep, but
    a history can span years and the day alone leaves him guessing which (TICKET-808)."""
    year, month, dom = iso_date.split("-")
    return f"{dom} {MONTHS[int(month) - 1]} {year}"


TRADER_ZONE = ZoneInfo("Asia/Kolkata")
"""Where every trader is. The database keeps instants in UTC (db.types.AwareDateTime)."""


def local_day(at: datetime) -> str:
    """The day an instant fell on in India, as day() writes it (TICKET-862).

    A row's own timestamp - when a file was read, a consent given, a number declared - is
    stored in UTC, and anything after 18:30 UTC is already the next day for the trader.
    Rendering it as stored dated it by the server's day, a day out from the trades on the
    same page. A naive value is refused, as the database refuses one (ctr_v1 4.3).
    """
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("a timestamp must carry its zone to be dated")
    return day(at.astimezone(TRADER_ZONE).date().isoformat())


def book_in_a_sentence(book: str) -> str:
    """A trade_book name inside a sentence: "were crude options", "were NIFTY options"."""
    return book[0].lower() + book[1:] if book[1:2].islower() else book


_FIGURE_FILTERS = {
    write.__name__: through_figure(write)
    for write in (rupees_on_a_trade, rupees, count, minutes, hold, lots, price, signed_percent,
                  out_of_a_hundred)
}
"""One of each, so every environment holds the same filter."""


def day_link(iso_date: str):
    """A trading day as day() writes it, opening that day: its trades and its journal (TICKET-905)."""
    from markupsafe import Markup
    return Markup('<a class="figure-link" href="/mirror/day/{}">{}</a>').format(iso_date, day(iso_date))


def identifier(value):
    """An identifier a trader may quote back - a version hash, an adapter name - written as text,
    never as a figure. A short git hash is all digits about one time in 27 (6145022), and as a
    bare value it would read, and be checked, as a number (TICKET-952)."""
    from services.production.api.figures import Written
    return Written(value)


def opens(value):
    """A figure as a link to its trades when it has any, else its plain text (figures.opened)."""
    from services.production.api.figures import as_text
    return as_text(value)


def register(env) -> None:
    """Make the filters available to every template the app renders. A figure goes through the
    same filter as a plain value, so writing one changes nothing on the page."""
    env.filters.update(tone=tone, day=day, local_day=local_day, book_in_a_sentence=book_in_a_sentence,
                       day_link=day_link, opens=opens, identifier=identifier, **_FIGURE_FILTERS)
    env.globals["Figure"] = Figure
