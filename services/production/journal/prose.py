"""Counted facts, rendered as prose (PRD 7.3).

The register, in the PRD's words: the quiet colleague who keeps the ledger. Neither
congratulatory nor scolding, and never surprised.

Every sentence here is a counted fact. Comparison to his own baseline is allowed
because the baseline is also counted; comparison to anyone else is not, because v1
has no population. Nothing names a cause, grades, praises, scolds or suggests.

Why this is templating rather than a language model: PRD 7.5 and the Manual both
require every number in the prose to resolve to a field, and the thesis reserves
narration for promoted Findings. A model that writes 'your size crept up' when the
field says the median was unchanged has invented something, and there is no way to
test that it will not. These sentences can only say what the facts contain.

Small numbers are words and large ones are figures, which is ordinary English and
also keeps a sentence from reading like a spreadsheet: 'Six trades, net -Rs 8,000'.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

WORDS = {
    0: "No", 1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six",
    7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten", 11: "Eleven", 12: "Twelve",
}


def _count(n: int, *, capital: bool = True) -> str:
    """Small numbers as words. Anything past twelve is a figure."""
    if n in WORDS:
        word = WORDS[n]
        return word if capital else word.lower()
    return str(n)


def _lots(value: Decimal) -> str:
    """Lots to one decimal place at most. Three is precision we do not have."""
    rounded = value.quantize(Decimal("0.1"))
    return f"{rounded:g}"


def _plural(n: Decimal | int, word: str) -> str:
    return word if Decimal(str(n)) == 1 else word + "s"


def _rupees(amount: str | Decimal) -> str:
    value = Decimal(str(amount))
    sign = "−" if value < 0 else ""
    return f"{sign}₹{abs(value):,.0f}"


def _clock(hour: int) -> str:
    return f"{hour:02d}:00"


def _heading(facts: dict[str, Any]) -> str:
    period = facts["period"]
    if period["unit"] == "day":
        day = date.fromisoformat(period["start"])
        return day.strftime("%A %-d %B %Y")
    if period["unit"] == "week":
        start = date.fromisoformat(period["start"])
        end = date.fromisoformat(period["end"])
        return f"{start.strftime('%-d %B')} to {end.strftime('%-d %B %Y')}"
    start = date.fromisoformat(period["start"])
    end = date.fromisoformat(period["end"])
    if period["start"] == period["end"]:
        return start.strftime("%-d %B %Y")
    return f"{start.strftime('%-d %B')} to {end.strftime('%-d %B %Y')}"


def _what_happened(facts: dict[str, Any]) -> str:
    trades = facts["trades"]
    count = trades["count"]
    net = _rupees(trades["net"])

    when = ""
    if trades["first_hour"] is not None:
        if trades["all_before_noon"]:
            when = ", all before noon"
        elif trades["first_hour"] != trades["last_hour"]:
            when = f", between {_clock(trades['first_hour'])} and {_clock(trades['last_hour'])}"

    outcome = ""
    if trades["wins"] or trades["losses"]:
        groups = [
            ("closed up", trades["wins"]),
            ("closed down", trades["losses"]),
            ("finished level", trades["scratches"]),
        ]
        present = [(phrase, n) for phrase, n in groups if n]
        if len(present) == 1:
            # One outcome covering the whole period would otherwise print the same
            # number in two consecutive sentences -- "Eight trades, all before noon.
            # Net -12,000. Eight closed down." Saying "All eight" makes the second
            # sentence a fact about the first rather than a repetition of it.
            phrase, n = present[0]
            outcome = (f" It {phrase}." if n == 1
                       else f" All {_count(n, capital=False)} {phrase}.")
        else:
            parts = [f"{_count(n, capital=False)} {phrase}" for phrase, n in present]
            outcome = " " + ", ".join(parts).capitalize() + "."

    word = "trade" if count == 1 else "trades"
    return f"{_count(count)} {word}{when}. Net {net}.{outcome}"


def _the_behaviour(facts: dict[str, Any]) -> str:
    after = facts["after_two_straight_losses"]
    if not after["today"]:
        return ""
    count = after["today"]
    were = "was" if count == 1 else "were"
    them = "it" if count == 1 else "them"
    days = after["days_it_happened"]
    total = after["your_trading_days"]
    # The baseline is across his whole history, and the sentence has to say so --
    # the same figure appears in every Journal, and without "across everything you
    # have uploaded" a trader reading two of them takes it for today's number.
    return (
        f"{_count(count)} {were} opened when the two trades before {them} had both "
        f"closed at a loss. Across everything you have uploaded that has happened "
        f"on {_count(days, capital=False)} of {_count(total, capital=False)} "
        f"trading {_plural(total, 'day')}."
    )


def _against_normal(facts: dict[str, Any]) -> str:
    against = facts["against_your_normal"]
    normal = Decimal(against["your_normal_day"])
    lots_today = Decimal(against["lots_today"])
    lots_usually = Decimal(against["lots_usually"])

    today = Decimal(str(against["trades_today"]))
    # A median of 4.5 is a real figure but "4.5 trades" is not how anyone speaks.
    # A fractional normal day is read aloud as the two counts it sits between.
    floor = int(normal)
    normal_text = (
        f"{floor:g}" if normal == floor else f"{floor} or {floor + 1}"
    )
    # Only worth a sentence when the day was not a normal one. "Four trades against
    # your normal day of four and a half" tells him nothing, and eight Journals all
    # carrying it turns the comparison into wallpaper.
    sentence = ""
    if normal > 0 and abs(today - normal) / normal >= Decimal("0.4"):
        direction = "more than" if today > normal else "fewer than"
        sentence = (
            f"That is {direction} your normal day of {normal_text} "
            f"{_plural(normal, 'trade')}."
        )

    # Size is only worth a sentence when it actually moved. Comparing 1.0 to 1.075
    # and calling it a change is noise dressed as an observation.
    today_lots = _lots(lots_today)
    usual_lots = _lots(lots_usually)
    # Within a tenth of a lot is not a change in size, whatever the raw averages
    # say. "1.0 against your usual 1.1" invites him to read a difference that is an
    # artefact of two round numbers and an odd lot.
    if abs(lots_today - lots_usually) >= Decimal("0.2"):
        sentence += (
            f" Your average size was {today_lots} "
            f"{_plural(Decimal(today_lots), 'lot')} against your usual {usual_lots}."
        )
    return sentence.strip()


def _the_blank_stop(facts: dict[str, Any]) -> str:
    """PRD 7.4: said once, without comment. No urging, no explanation."""
    stop = facts["planned_sl"]
    missing = stop["losing_trades_without_one"]
    if not missing or stop["said_before"]:
        return ""
    word = "trade that lost has" if missing == 1 else "trades that lost have"
    return f"No planned stop is recorded on {_count(missing, capital=False)} {word.replace('trade that lost has', 'trade that lost').replace('trades that lost have', 'trades that lost')}."


def render(facts: dict[str, Any]) -> str:
    """One Journal, as paragraphs. Empty sections produce nothing, not a placeholder."""
    # The day-shape sentence sits with the count it qualifies. Placed after the
    # behaviour paragraph, "That is against a normal day" reads as a comment on the
    # trades after losses rather than on the day -- the referent is whatever
    # preceded it, and a trader reads in order.
    opener = _what_happened(facts)
    shape = _against_normal(facts)
    if shape:
        opener = f"{opener} {shape}"

    paragraphs = [opener, _the_behaviour(facts), _the_blank_stop(facts)]
    body = "\n\n".join(p for p in paragraphs if p)

    # The charges note is a property of his FILE, not of this day. Said once, at the
    # foot, rather than inside every figure in every Journal he will ever read.
    if not facts["fees_available"]:
        body += "\n\nEvery figure here is gross: your export carries no charges."
    return body
