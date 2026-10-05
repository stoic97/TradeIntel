"""Canonical serialisation of an import, for the determinism gate.

Methodology s12 requires data artifacts to have an **exact canonical hash, identical
across runs and across platforms** -- a difference is a bug, not a tolerance. This
module is that canonical form: a plain dict with sorted keys and every value rendered
as a deterministic string, so two runs can be compared byte for byte and a golden
file can be committed beside the fixture that produced it.

Decimals are written with ``str()``, which is exact and stable for a Decimal -- no
rounding happens here. A number that rounds for display rounds at the presentation
boundary, never in the record (s6.5).

Content hashes (``fill_id``, ``trip_id``) are included deliberately. If a change
alters what a fill or a trip *is*, those ids move, and the golden catches it.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from services.production.ctr.adapters.base import ParseResult
from services.production.ctr.reconstruct import ReconstructionResult
from services.shared.schemas.ctr_v1 import SCHEMA_VERSION, Fill, RoundTrip


def _d(value: Decimal | None) -> str | None:
    """Exact, stable text for a Decimal. No rounding."""
    return None if value is None else str(value)


def _fill(f: Fill) -> dict[str, Any]:
    return {
        "fill_id": f.fill_id,
        "ts": f.ts.isoformat(),
        "exchange": f.exchange,
        "segment": f.segment.value,
        "symbol": f.symbol,
        "expiry": f.expiry.isoformat() if f.expiry else None,
        "option_type": f.option_type.value if f.option_type else None,
        "strike": _d(f.strike),
        "side": f.side.value,
        "quantity": f.quantity,
        "price": _d(f.price),
        "quoted_price": _d(f.quoted_price),
        "trade_value": _d(f.trade_value),
        "product": f.product,
    }


def _trip(t: RoundTrip) -> dict[str, Any]:
    return {
        "trip_id": t.trip_id,
        "exchange": t.exchange,
        "segment": t.segment.value,
        "symbol": t.symbol,
        "expiry": t.expiry.isoformat() if t.expiry else None,
        "option_type": t.option_type.value if t.option_type else None,
        "strike": _d(t.strike),
        "direction": t.direction.value,
        "entry_ts": t.entry_ts.isoformat(),
        "exit_ts": t.exit_ts.isoformat(),
        "holding_seconds": t.holding_seconds,
        "quantity": t.quantity,
        "entry_price": _d(t.entry_price),
        "exit_price": _d(t.exit_price),
        "gross_pnl": _d(t.gross_pnl),
        "fees": _d(t.fees),
        "net_pnl": _d(t.net_pnl),
        "risk_unit": _d(t.risk_unit),
        "risk_unit_source": t.risk_unit_source.value,
        "r_multiple": _d(t.r_multiple),
        "fill_ids": sorted(t.fill_ids),
    }


def snapshot(parsed: ParseResult, recon: ReconstructionResult) -> dict[str, Any]:
    """The canonical dict for one import. Deterministic for a given input."""
    return {
        "schema_version": SCHEMA_VERSION,
        "parse": {
            "format_id": parsed.format_id,
            "rows_in": parsed.rows_in,
            "fills_parsed": len(parsed.fills),
            "fees_available": parsed.fees_available,
            "rejected": [
                {"row": r.row, "reason": r.reason}
                for r in sorted(parsed.rejected, key=lambda r: r.row)
            ],
        },
        "fills": [_fill(f) for f in parsed.fills],
        "reconstruction": {
            "quantity_in": recon.quantity_in,
            "fees_available": recon.fees_available,
            "round_trips": [_trip(t) for t in recon.round_trips],
            "open_positions": [
                {
                    "contract_key": o.contract_key,
                    "symbol": o.symbol,
                    "direction": o.direction.value,
                    "quantity": o.quantity,
                    "opened_at": o.opened_at.isoformat(),
                    "fill_ids": sorted(o.fill_ids),
                    "reason": o.reason,
                }
                for o in recon.open_positions
            ],
            "skipped": [
                {
                    "contract_key": s.contract_key,
                    "symbol": s.symbol,
                    "direction": s.direction.value,
                    "quantity": s.quantity,
                    "reason": s.reason,
                    "fill_ids": sorted(s.fill_ids),
                }
                for s in recon.skipped
            ],
        },
    }


def canonical_json(snap: dict[str, Any]) -> str:
    """Sorted keys, fixed separators, trailing newline. Byte-comparable."""
    return json.dumps(snap, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def digest(snap: dict[str, Any]) -> str:
    """SHA-256 of the canonical form."""
    return hashlib.sha256(canonical_json(snap).encode("utf-8")).hexdigest()
