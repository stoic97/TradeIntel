"""After you closed (TICKET-1009). RED stub: the names exist, the behaviour does not."""

KEY = "after-close"
HORIZON = 30
NOT_WORKED_OUT = "its figures aren't worked out yet"


def _todo(*a, **kw):
    raise NotImplementedError("TICKET-1009")


def load(sess, imp):
    return {}


def view(ctx, pick=None):
    return {"enough": False, "came_back": 0, "losers": 0, "came_back_ids": [], "minimum": 30,
            "reasons": [], "chips": [], "measured": 0, "not_measured": 0, "underlying": None,
            "winners": 0, "rows": [], "losers_median": (), "winners_median": ()}


came_back_at = figure = geometry = _todo
