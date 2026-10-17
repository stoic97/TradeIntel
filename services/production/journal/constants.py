"""The product constants, in one place, each with the argument for it.

PRD 13.4 and 14: these are chosen numbers, not fitted ones. None is derived from any
trader's history, and the kickoff changes any of them by editing one line here.

``ARGUMENTS`` is not decoration. A constant whose reasoning lives only in someone's
memory becomes unchallengeable: nobody can argue with a number whose basis they
cannot read. A test asserts every constant here has an argument long enough to
review.
"""

from __future__ import annotations

DENSITY_THRESHOLD_TRIPS_PER_DAY = 2
JOURNALS_ON_SURFACE = 5
WTP_DAYS_SINCE_FIRST_UPLOAD = 14
WTP_PRICE_INR = 500
DEFAULT_TRIPS_PER_JOURNAL = 10

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_ROWS = 50_000

ARGUMENTS: dict[str, str] = {
    "DENSITY_THRESHOLD_TRIPS_PER_DAY": (
        "A trading day with one trade on it makes a thin Journal: there is nothing to "
        "compare within the day, and a daily entry would mostly repeat the trade. Two "
        "is the smallest count at which a day holds a comparison. Below it the Journal "
        "groups by trade count instead. The trader's own setting always overrides."
    ),
    "JOURNALS_ON_SURFACE": (
        "A historical upload can generate thirty Journals at once, and thirty entries "
        "on a screen is an archive, not a read. Five is about what fits on a phone "
        "without scrolling past the fold; the rest are one tap away in the catch-up "
        "list, which is where they belong rather than gone."
    ),
    "WTP_DAYS_SINCE_FIRST_UPLOAD": (
        "The willingness-to-pay question must not fire on day one of a backfill, when "
        "the trader has read nothing and used nothing. Fourteen days is long enough "
        "that he has either come back or not -- both of which are answers -- and "
        "short enough to ask while the product is still fresh to him."
    ),
    "WTP_PRICE_INR": (
        "A placeholder price, not a decided one. It exists so the question is concrete "
        "rather than abstract: 'would you pay for this' gets a polite yes, 'would you "
        "pay Rs 500 a month' gets a real answer. The number is the kickoff's to set, "
        "and the answer is stored with it so a later change is interpretable."
    ),
    "DEFAULT_TRIPS_PER_JOURNAL": (
        "When a trader's days are too thin for a daily Journal, ten trades is a "
        "stretch of trading he can remember as a stretch -- long enough to hold a "
        "pattern, short enough that the first trade in it is still recent."
    ),
    "MAX_UPLOAD_BYTES": (
        "Uploads are processed synchronously (ADR 007), so a pathological file would "
        "hold the request open. Ten megabytes is far beyond any tradebook we have "
        "seen -- the largest real history so far is well under one -- and the limit is "
        "stated on the upload page rather than discovered by failing."
    ),
    "MAX_UPLOAD_ROWS": (
        "The row equivalent of the byte cap, since a file can be small and still have "
        "very many rows. Fifty thousand is roughly fifteen times the largest real "
        "history we hold."
    ),
}
