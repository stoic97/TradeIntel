"""The admin command line. Creates accounts, imports a file, prints a review.

Two rules it keeps, both from the design's sealing section:

**It reads no trade data.** ``import`` prints counts, outcomes and reasons -- never a
rupee figure, never a row's contents. Debugging happens on fixtures and
development-data accounts, not by reading a partner's history from a terminal.

**Every action is logged.** Creating a trader, resetting a password and marking an
account as development data each write an ``admin_action`` row (thesis 19.1).

Usage:

    python -m services.production.api.cli init-db
    python -m services.production.api.cli create-trader --login-id rikk --name "Rikk"
    python -m services.production.api.cli invite --code DEV-1
    python -m services.production.api.cli classify --login-id rikk --development-data
    python -m services.production.api.cli import --login-id rikk --file path/to/export.csv
    python -m services.production.api.cli review --import-id 1
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from services.production.ctr.intake import persist
from services.production.ctr.intake import pipeline as pl
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.production.journal import generate as gen

DEFAULT_DB = os.environ.get("SCOPE_DB", "sqlite:///scope.db")
STORE = Path(os.environ.get("SCOPE_FILES", "./_files"))


def code_version() -> str:
    """The commit this import ran on. 'dirty' when the tree has uncommitted changes."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        ).stdout.strip()
        return f"{sha}-dirty" if dirty else sha
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _log(sess, actor: str, action: str, target: str | None) -> None:
    sess.add(
        m.AdminAction(actor=actor, action=action, target=target, at=datetime.now(UTC))
    )


def _trader(sess, login_id: str) -> m.Trader:
    trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == login_id)).first()
    if trader is None:
        raise SystemExit(f"no trader with login id {login_id!r}")
    return trader


def cmd_init_db(args: argparse.Namespace) -> None:
    engine = make_engine(args.db)
    run_migrations(engine)
    print(f"schema up to date: {args.db}")


def cmd_create_trader(args: argparse.Namespace) -> None:
    engine = make_engine(args.db)
    run_migrations(engine)
    with make_session(engine) as sess:
        trader = m.Trader(
            display_name=args.name,
            login_id=args.login_id,
            password_hash="(not set: phase 2)",
            created_at=datetime.now(UTC),
            development_data=args.development_data,
        )
        sess.add(trader)
        sess.flush()
        _log(sess, os.environ.get("USER", "admin"), "create_trader", args.login_id)
        sess.commit()
        flag = " (development data)" if args.development_data else ""
        print(f"trader {trader.id}: {args.login_id}{flag}")


def cmd_classify(args: argparse.Namespace) -> None:
    """Classify an existing account's history as development data, or as real.

    ``create-trader`` could set this at creation and nothing could change it
    afterwards, which is the wrong way round: an account is created through an
    invite, where nobody is asked this, and the classification is a decision made
    about a partner's history after talking to him.

    It is not a cosmetic flag. A development-data account may be shown the
    unreviewed consent text, and PRD decision 21 says that partner receives an
    addendum telling him his history was used to build the product. Printing the
    reminder is the closest this command can come to making that happen.
    """
    engine = make_engine(args.db)
    run_migrations(engine)
    with make_session(engine) as sess:
        trader = _trader(sess, args.login_id)
        before = trader.development_data
        trader.development_data = args.development_data
        action = "classify_development_data" if args.development_data else "classify_real"
        _log(sess, os.environ.get("USER", "admin"), action, args.login_id)
        sess.commit()

    if before == args.development_data:
        print(f"{args.login_id}: unchanged")
        return
    if args.development_data:
        print(f"{args.login_id}: development data")
        print("  send the addendum: his history was used to build the product "
              "(PRD decision 21)")
    else:
        print(f"{args.login_id}: a real account")
        print("  he can no longer be shown unreviewed consent text")


def cmd_invite(args: argparse.Namespace) -> None:
    """Mint an invite code and print the URL it opens.

    Access is invite-only (PRD 5.1) and ``create-trader`` cannot produce a trader who
    can sign in -- it writes a placeholder password hash, because a trader sets his
    own password through the invite. So without this command the only way to sign up
    locally was to write the row by hand, which is why every walkthrough so far began
    by reconstructing one.
    """
    engine = make_engine(args.db)
    run_migrations(engine)
    with make_session(engine) as sess:
        taken = sess.scalars(
            select(m.InviteCode).where(m.InviteCode.code == args.code)
        ).first()
        if taken is not None:
            raise SystemExit(f"invite code {args.code!r} already exists")
        sess.add(m.InviteCode(code=args.code, created_at=datetime.now(UTC)))
        _log(sess, os.environ.get("USER", "admin"), "create_invite", args.code)
        sess.commit()
    print(f"invite {args.code}: http://127.0.0.1:8000/invite/{args.code}")


def cmd_import(args: argparse.Namespace) -> None:
    path = Path(args.file)
    text = path.read_text()
    engine = make_engine(args.db)
    run_migrations(engine)
    STORE.mkdir(parents=True, exist_ok=True)

    with make_session(engine) as sess:
        trader = _trader(sess, args.login_id)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        stored = STORE / f"{digest}{path.suffix}"
        if not stored.exists():
            stored.write_text(text)

        existing = persist.existing_days(
            sess, trader=trader, source_account=args.source_account
        )
        plan = pl.plan_import(
            text,
            context=pl.ImportContext(
                trader_id=str(trader.id),
                source_account=args.source_account,
                code_version=code_version(),
                existing_days=existing,
                export_date=args.export_date,
                export_date_source="admin" if args.export_date else None,
            ),
            production=args.production,
        )
        imp = persist.write_plan(
            sess, trader=trader, plan=plan, raw_sha256=digest,
            original_name=path.name, stored_path=str(stored), size=path.stat().st_size,
            source_account=args.source_account,
        )
        sess.commit()
        gen.for_import(sess, trader=trader)
        sess.commit()
        print(f"import {imp.id}: {imp.outcome.value}")
        _print_review(sess, imp)


def cmd_review(args: argparse.Namespace) -> None:
    engine = make_engine(args.db)
    with make_session(engine) as sess:
        imp = sess.get(m.Import, args.import_id)
        if imp is None:
            raise SystemExit(f"no import {args.import_id}")
        _print_review(sess, imp)


def _print_review(sess, imp: m.Import) -> None:
    """Counts, outcomes and reasons. No trade data (design section 5, sealing)."""
    print(f"  outcome        {imp.outcome.value}")
    if imp.rejection_text:
        print(f"  rejection      {imp.rejection_text}")
        return
    print(f"  rows           {imp.rows_in} in, {imp.rows_parsed} parsed, "
          f"{imp.rows_excluded} excluded")
    print(f"  trips          {imp.trips_reconstructed} reconstructed, "
          f"{imp.trips_refused} refused")
    print(f"  fees           {'present' if imp.fees_available else 'absent (figures are gross)'}")
    print(f"  journal unit   {imp.density_default_unit} (density default)")
    partial = imp.partial_fields or "[]"
    if "instrument profile" in partial:
        print("  profiles       MISSING for some instruments - see partial_fields")
    print(f"  versions       code {imp.code_version}, adapter {imp.adapter_id} "
          f"{imp.adapter_version}, profiles {imp.profile_versions}")
    print(f"  digest         {imp.snapshot_digest}")

    flagged = sess.scalars(
        select(m.ImportRow).where(
            m.ImportRow.import_id == imp.id, m.ImportRow.flag.is_not(None)
        )
    ).all()
    if flagged:
        groups = {r.dup_group for r in flagged}
        print(f"  duplicates     {len(flagged)} rows in {len(groups)} groups, flagged not dropped")
        print("                 trip counts include them until the trader confirms")

    days = sess.scalars(
        select(m.TradingDayVersion).where(m.TradingDayVersion.import_id == imp.id)
    ).all()
    for day in days:
        shrank = "  <- SHRANK" if day.day_shrank else ""
        print(f"  {day.trading_day}     {day.rows_before} -> {day.rows_after} "
              f"({day.diff.value}){shrank}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="scope", description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db").set_defaults(func=cmd_init_db)

    create = sub.add_parser("create-trader")
    create.add_argument("--login-id", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--development-data", action="store_true")
    create.set_defaults(func=cmd_create_trader)

    imp = sub.add_parser("import")
    imp.add_argument("--login-id", required=True)
    imp.add_argument("--file", required=True)
    imp.add_argument("--source-account", default="A")
    imp.add_argument("--export-date")
    imp.add_argument("--production", action="store_true",
                     help="refuse an unverified broker file map (TD-024)")
    imp.set_defaults(func=cmd_import)

    classify = sub.add_parser("classify")
    classify.add_argument("--login-id", required=True)
    how = classify.add_mutually_exclusive_group(required=True)
    how.add_argument("--development-data", dest="development_data",
                     action="store_true")
    how.add_argument("--real", dest="development_data", action="store_false")
    classify.set_defaults(func=cmd_classify)

    invite = sub.add_parser("invite")
    invite.add_argument("--code", required=True)
    invite.set_defaults(func=cmd_invite)

    review = sub.add_parser("review")
    review.add_argument("--import-id", type=int, required=True)
    review.set_defaults(func=cmd_review)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main(sys.argv[1:])
