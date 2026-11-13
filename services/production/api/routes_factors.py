"""/factors: the published factor map (TICKET-921), open to anyone.

The list is ``factor_map.FACTORS``. A signed-in trader with a record also sees, per
factor, whether his own file let Scope look at it, read from what the report already
decides (eligibility, each fact's state, the trade-list filters). The page computes
nothing and carries no figure from anyone's file.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from services.production.api import factor_map as FM
from services.production.api import scope_facts as SF
from services.production.api import trade_list as TL
from services.production.api.routes_identity import current_trader, page
from services.production.ctr.profiles import registry as profiles
from services.production.db.session import make_session
from services.production.eligibility import assess as el
from services.production.mirror import loader

router = APIRouter()


def _his_file(request: Request) -> dict[str, str] | None:
    """Factor name to what his file let Scope do with it; None without a record."""
    with make_session(request.app.state.engine) as sess:
        trader = current_trader(request, sess)
        if trader is None:
            return None
        try:
            trips, imp = loader.load_for(sess, trader)
        except (profiles.UnknownInstrument, loader.MisdeclaredQuantityUnit):
            # the report shows his record's own refusal; the map still opens, as published
            return None
        if not trips:
            return None
        expiries = loader.expiries_for(sess, imp)
    eligibility = el.assess(trips)
    enough = frozenset(v.test.id for v in eligibility.enough)
    short = frozenset(v.test.id for v in eligibility.short)
    figs = SF.facts(SF.record_context(trips), imp)
    states = {key: fig.get("state") for key, fig in figs.items()}
    seen = frozenset(f.name for f in TL.FILTERS
                     if any(f.read(t, expiries) is not None for t in trips))
    return {f.name: FM.in_file(f, enough=enough, short=short, fact_states=states,
                               filters_seen=seen, has_charges=bool(imp.fees_available)).value
            for f in FM.FACTORS}


@router.get("/factors", response_class=HTMLResponse)
def factors(request: Request):
    his = _his_file(request)
    families = [(family, [f for f in FM.FACTORS if f.family == family])
                for family in FM.FAMILIES]
    return page(request, "factors.html", title="What Scope looks at", families=families,
                statuses=FM.STATUS_MEANS, his=his)
