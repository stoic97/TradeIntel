"""The demo tradebook (TICKET-842): what it is, and how to tell it from a real upload.

A visitor without his broker export can load a synthetic Dhan tradebook into his own
account and see the report. It is an ordinary upload through the ordinary pipeline, so
everything the report shows is the pipeline's reading of that file. Three things set it
apart, all from one fact, its source account:

* **Its own source account.** A trading day's versions are kept per source account
  (``persist.existing_days``), so a real upload never compares itself against demo days.
* **It says so.** Every page drawn from it carries one plain line (``LINE``), and a page
  drawn from a real upload never does (``api.routes_identity.page``).
* **A real record replaces it.** Once a real upload has trades, the demo and everything
  derived from it is removed before the real import is written
  (``accounts.deletion.remove_demo``), so the real upload is version 1 with nothing
  behind it, its Journals start fresh, and nothing written on a demo Journal is carried.
  Until then "Delete everything" takes it like any other upload (TICKET-802).

The file is generated, never edited: ``data/fixtures/demo/scope_demo.py`` with its
committed seed. No real trader's rows (README rule 1).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.production.db import models as m

ACCOUNT = "DEMO"
"""The source account a demo upload is planned under; a real upload's is "A"."""

FILE = Path(__file__).resolve().parents[2] / "data/fixtures/demo/scope_demo_tradebook.csv"
FILE_NAME = "Scope demo tradebook.csv"
EXPORT_DATE = "2026-09-01"
"""The day after the file's last trade: the day it would have been downloaded."""

LINE = "This is a demo file, not your trading."


def is_demo(imp) -> bool:
    """Whether this import is the demo. Anything without a source account is not."""
    return getattr(imp, "source_account", None) == ACCOUNT


def current_import(sess: Session, trader: m.Trader) -> m.Import | None:
    """The record the report reads: the newest import with trades (``loader.current_import``)."""
    return sess.scalars(
        select(m.Import)
        .join(m.Trip, m.Trip.import_id == m.Import.id)
        .where(m.Import.trader_id == trader.id)
        .order_by(m.Import.id.desc())
        .limit(1)
    ).first()


def demo_import(sess: Session, trader: m.Trader) -> m.Import | None:
    """His demo upload, if he has one."""
    return sess.scalars(
        select(m.Import)
        .where(m.Import.trader_id == trader.id, m.Import.source_account == ACCOUNT)
        .order_by(m.Import.id.desc())
        .limit(1)
    ).first()


def has_real_record(sess: Session, trader: m.Trader) -> bool:
    """Whether he has a real upload with trades. Then the demo is neither offered nor taken:
    it would become the record the report reads, and hide his own."""
    return sess.scalars(
        select(m.Import.id)
        .join(m.Trip, m.Trip.import_id == m.Import.id)
        .where(m.Import.trader_id == trader.id, m.Import.source_account != ACCOUNT)
        .limit(1)
    ).first() is not None

from services.research import evaluation  # noqa: F401  deliberate Rule 5 breach (throwaway, do not merge)
