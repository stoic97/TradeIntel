#!/usr/bin/env python3
"""TICKET-990 - classify a release range as Path A / Path B / read by hand.

Reads the upgrade() body of every migration added or changed between two refs
and classifies it by the Alembic operation names it calls.  Nothing in
downgrade() is read: a drop that runs only on a rollback does not make a
release destructive.  op.drop_column and batch.drop_column are the same
finding, because the classification is by operation name, not by the object
the call is made on.

Read-only: two git plumbing commands, no checkout, no database, no network.

Usage:  python3 classify_release.py <live-ref> <tag-ref>

Exit codes
  0  PATH A        additive only, or no migration in the range
  1  PATH B        an upgrade() drops or alters something
  2  READ BY HAND  something this check will not rule on
  3  DID NOT RUN   git failed, the arguments are wrong, or this check broke

Known limit: an upgrade() that calls a helper defined in the same file is
answered READ BY HAND rather than followed.
"""

from __future__ import annotations

import ast
import subprocess
import sys

MIGRATIONS = "migrations/versions"

PATH_A, PATH_B, BY_HAND, DID_NOT_RUN = 0, 1, 2, 3
_RANK = {PATH_A: 0, BY_HAND: 1, PATH_B: 2}

DESTRUCTIVE = frozenset(
    {"drop_table", "drop_column", "drop_index", "drop_constraint", "alter_column"}
)
ADDITIVE = frozenset({"create_table", "create_index"})
HAND = frozenset({"execute", "bulk_insert"})
NEUTRAL = frozenset({"batch_alter_table", "f", "get_bind", "get_context"})


def _worse(a: int, b: int) -> int:
    return a if _RANK[a] >= _RANK[b] else b


def _batch_aliases(fn: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "batch_alter_table"
                    and isinstance(item.optional_vars, ast.Name)
                ):
                    names.add(item.optional_vars.id)
    return names


def _op_calls(fn: ast.AST, aliases: set[str]) -> list[tuple[str, ast.Call]]:
    found: list[tuple[str, ast.Call]] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            base = node.func.value
            if isinstance(base, ast.Name) and (base.id == "op" or base.id in aliases):
                found.append((node.func.attr, node))
    return found


def _local_helper(fn: ast.AST, helpers: set[str]) -> str | None:
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in helpers
        ):
            return node.func.id
    return None


def _add_column_nullable(call: ast.Call) -> bool | None:
    """True = plainly nullable, False = plainly not, None = cannot tell."""

    def _is_column(node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        if isinstance(node.func, ast.Attribute):
            return node.func.attr == "Column"
        if isinstance(node.func, ast.Name):
            return node.func.id == "Column"
        return False

    for arg in list(call.args) + [kw.value for kw in call.keywords]:
        if _is_column(arg):
            for kw in arg.keywords:
                if kw.arg == "nullable":
                    if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, bool):
                        return kw.value.value
                    return None
            return True
    return None


def classify_source(source: str, label: str = "<source>") -> tuple[int, list[str]]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return BY_HAND, [f"{label}: will not parse ({exc.msg})"]

    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    upgrade = functions.get("upgrade")
    if upgrade is None:
        return BY_HAND, [f"{label}: no upgrade() at module level"]

    helper = _local_helper(upgrade, set(functions) - {"upgrade", "downgrade"})
    if helper is not None:
        return BY_HAND, [f"{label}: upgrade() calls {helper}(), not read by this check"]

    calls = _op_calls(upgrade, _batch_aliases(upgrade))
    if not calls:
        return BY_HAND, [f"{label}: upgrade() makes no op.* or batch.* call"]

    verdict = PATH_A
    reasons: list[str] = []
    for name, node in calls:
        if name in DESTRUCTIVE:
            reasons.append(f"{label}: upgrade() calls {name}")
            verdict = _worse(verdict, PATH_B)
        elif name in HAND:
            reasons.append(f"{label}: upgrade() calls {name}")
            verdict = _worse(verdict, BY_HAND)
        elif name == "add_column":
            if _add_column_nullable(node) is not True:
                reasons.append(f"{label}: upgrade() adds a column that is not plainly nullable")
                verdict = _worse(verdict, BY_HAND)
        elif name in ADDITIVE or name in NEUTRAL:
            continue
        else:
            reasons.append(f"{label}: upgrade() calls {name}, not on the Path A list")
            verdict = _worse(verdict, BY_HAND)
    if verdict == PATH_A and not reasons:
        reasons.append(f"{label}: upgrade() is additive")
    return verdict, reasons


def _git(*args: str) -> str:
    done = subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", check=False
    )
    if done.returncode != 0:
        raise RuntimeError("git " + " ".join(args) + ": " + done.stderr.strip())
    return done.stdout


def classify_range(live: str, tag: str) -> tuple[int, list[str]]:
    listing = _git("diff", "--name-only", "--diff-filter=AM", live, tag, "--", MIGRATIONS)
    paths = [
        line.strip()
        for line in listing.splitlines()
        if line.strip().endswith(".py") and not line.strip().endswith("__init__.py")
    ]
    if not paths:
        return PATH_A, ["no migration added or changed in this range"]

    verdict = PATH_A
    reasons: list[str] = []
    for path in paths:
        one, why = classify_source(_git("show", f"{tag}:{path}"), path)
        reasons.extend(why)
        verdict = _worse(verdict, one)
    return verdict, reasons


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: classify_release.py <live-ref> <tag-ref>", file=sys.stderr)
        return DID_NOT_RUN
    try:
        verdict, reasons = classify_range(argv[1], argv[2])
    except Exception as exc:  # noqa: BLE001 - a broken check must not read as a path
        print(f"could not classify: {exc!r}", file=sys.stderr)
        return DID_NOT_RUN
    for reason in reasons:
        print(reason)
    return verdict


if __name__ == "__main__":
    sys.exit(main(sys.argv))
