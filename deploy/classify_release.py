#!/usr/bin/env python3
"""TICKET-990 - classify a release range as Path A / Path B / read by hand.

Reads the upgrade() body of every migration added, changed or removed between
two refs and classifies it by the Alembic operation names it calls.  Nothing in
downgrade() is read: a drop that runs only on a rollback does not make a
release destructive.  op.drop_column and batch.drop_column are the same
finding, because the classification is by operation name, not by the object the
call is made on.

Path A is the answer only when every call in upgrade() is one this check
recognises: an operation on op or on a with ... as <name> batch context, or a
constructor from sqlalchemy or a database types module.  Anything else - a
helper, an aliased or dotted op function, getattr, a call on a connection - is
answered READ BY HAND rather than assumed additive.

Rename detection is off, so a migration git would report as renamed is read at
its new path.  A migration that is gone at the tag is answered READ BY HAND.

Read-only: two git plumbing commands, no checkout, no database, no network.

Usage:  python3 classify_release.py <live-ref> <tag-ref>

Exit codes
  0  PATH A        additive only, or no migration in the range
  1  PATH B        an upgrade() drops or alters something
  2  READ BY HAND  something this check will not rule on
  3  DID NOT RUN   git failed, the arguments are wrong, or this check broke
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
HAND_OPS = frozenset({"execute", "bulk_insert", "get_bind", "get_context"})
OP_NEUTRAL = frozenset({"batch_alter_table", "f"})
SAFE_BUILTINS = frozenset(
    {
        "len", "str", "int", "bool", "float", "list", "dict", "tuple", "set",
        "range", "enumerate", "sorted", "repr",
    }
)
SAFE_MODULE_SUFFIXES = (".types",)


def _worse(a: int, b: int) -> int:
    return a if _RANK[a] >= _RANK[b] else b


def _is_safe_module(path: str) -> bool:
    return path.startswith("sqlalchemy") or path.endswith(SAFE_MODULE_SUFFIXES)


def _safe_names(tree: ast.Module) -> set[str]:
    """Names bound by an import of sqlalchemy or of a database types module."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_safe_module(alias.name):
                    names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                if _is_safe_module(module) or _is_safe_module(f"{module}.{alias.name}"):
                    names.add(alias.asname or alias.name)
    return names


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
            if any(kw.arg is None for kw in arg.keywords):
                return None  # nullable may be hidden in **kwargs
            for kw in arg.keywords:
                if kw.arg == "nullable":
                    if isinstance(kw.value, ast.Constant) and isinstance(
                        kw.value.value, bool
                    ):
                        return kw.value.value
                    return None
                if kw.arg == "primary_key":
                    return None
            return True
    return None


def _describe(func: ast.AST) -> str:
    try:
        text = ast.unparse(func)
    except Exception:  # noqa: BLE001 - only used for the printed reason
        return "a call"
    return text if len(text) <= 60 else text[:57] + "..."


def classify_source(source: str, label: str = "<source>") -> tuple[int, list[str]]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return BY_HAND, [f"{label}: will not parse ({exc.msg})"]

    upgrade = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
        ),
        None,
    )
    if upgrade is None:
        return BY_HAND, [f"{label}: no upgrade() at module level"]

    safe = _safe_names(tree) | SAFE_BUILTINS
    aliases = _batch_aliases(upgrade)

    verdict, reasons, saw_operation = PATH_A, [], False
    for node in ast.walk(upgrade):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and (func.value.id == "op" or func.value.id in aliases)
        ):
            saw_operation = True
            name = func.attr
            if name in DESTRUCTIVE:
                reasons.append(f"{label}: upgrade() calls {name}")
                verdict = _worse(verdict, PATH_B)
            elif name in HAND_OPS:
                reasons.append(f"{label}: upgrade() calls {name}")
                verdict = _worse(verdict, BY_HAND)
            elif name == "add_column":
                if _add_column_nullable(node) is not True:
                    reasons.append(
                        f"{label}: upgrade() adds a column that is not plainly nullable"
                    )
                    verdict = _worse(verdict, BY_HAND)
            elif name not in ADDITIVE and name not in OP_NEUTRAL:
                reasons.append(f"{label}: upgrade() calls {name}, not on the Path A list")
                verdict = _worse(verdict, BY_HAND)
            continue
        if isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name) and func.value.id in safe:
                continue
        elif isinstance(func, ast.Name) and func.id in safe:
            continue
        reasons.append(
            f"{label}: upgrade() makes a call this check does not read ({_describe(func)})"
        )
        verdict = _worse(verdict, BY_HAND)

    if not saw_operation and verdict == PATH_A:
        return BY_HAND, [f"{label}: upgrade() makes no op.* or batch.* operation"]
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


def _migrations(listing: str) -> list[str]:
    return [
        line.strip()
        for line in listing.splitlines()
        if line.strip().endswith(".py") and not line.strip().endswith("__init__.py")
    ]


def classify_range(live: str, tag: str) -> tuple[int, list[str]]:
    changed = _migrations(
        _git(
            "diff", "--name-only", "--no-renames", "--diff-filter=AM",
            live, tag, "--", MIGRATIONS,
        )
    )
    removed = _migrations(
        _git(
            "diff", "--name-only", "--no-renames", "--diff-filter=D",
            live, tag, "--", MIGRATIONS,
        )
    )
    if not changed and not removed:
        return PATH_A, ["no migration added, changed or removed in this range"]

    verdict, reasons = PATH_A, []
    for path in changed:
        one, why = classify_source(_git("show", f"{tag}:{path}"), path)
        reasons.extend(why)
        verdict = _worse(verdict, one)
    for path in removed:
        reasons.append(f"{path}: gone at {tag}, read this range by hand")
        verdict = _worse(verdict, BY_HAND)
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
