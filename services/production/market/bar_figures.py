"""Bar figures, worked out off the web app (TICKET-999). RED stub: names only."""

HORIZON, FAINT = 30, 200
PENDING, WAITING, DONE = "pending", "waiting", "done"
NO_DIRECTION = NO_SERIES = MONTH = NO_MONTH = WAITING_FOR_DAY = NO_ENTRY_BAR = "stub"


class Leg:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Position:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _todo(*a, **kw):
    raise NotImplementedError("TICKET-999")


measure = random_paths = summarise = evenly = run = crude_future_expiry = near_month = _todo
