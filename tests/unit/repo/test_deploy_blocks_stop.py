"""TICKET-1093: every pasted deploy block stops at its first failure and leaves the shell open.

The release train's blocks (d. Deploy the tag, e. Check production, Rollback) are pasted by a
person, as root, on the production droplet. A block that carries on after a failed step can
restart production on the wrong code (a failed checkout, then ``systemctl restart``), and a
block that ends in ``exit 1`` closes the shell it was pasted into. Each block is extracted
from the runbook and run in bash, straight and inside a nested bash, with stubs for the
commands that touch the box and temp dirs for /srv/scope, /etc and /var/backups. Tag, shas
and paths are made up.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path("docs/runbooks/deploy.md").read_text(encoding="utf-8")

TAG = "v2099.01.02"
PREV = "v2099.01.01"
RESTORE = "/var/backups/scope/restore-made-up.db"

SECTIONS = {
    "d": ("### d. Deploy the tag", "### e. Check production"),
    "e": ("### e. Check production", "### f. Log it"),
    "rollback": ("### Rollback", "### Hotfixes"),
}


def _blocks(s: str) -> list[str]:
    """Each indented command block in the section, as one string."""
    out, cur = [], []
    for line in s.splitlines():
        if line.startswith("    "):
            cur.append(line.strip())
        elif cur:
            out.append("\n".join(cur)); cur = []
    if cur:
        out.append("\n".join(cur))
    return out


def _section(key: str) -> str:
    start, end = SECTIONS[key]
    assert start in DEPLOY and end in DEPLOY, (start, end)
    return DEPLOY[DEPLOY.index(start):DEPLOY.index(end)]


# a block is found by what it does, so a re-worded runbook keeps its tests
FIND = {
    "where": ("d", lambda b: "git describe" in b and "git fetch" in b),
    "path-a": ("d", lambda b: "systemctl restart scope" in b and "systemctl stop scope" not in b),
    "path-b": ("d", lambda b: "systemctl stop scope" in b and "systemctl start scope" in b),
    "check": ("e", lambda b: "journalctl" in b),
    "tags": ("rollback", lambda b: "git tag --sort" in b),
    "rollback-a": ("rollback", lambda b: "systemctl restart scope" in b and "systemctl stop scope" not in b),
    "rollback-b": ("rollback", lambda b: "systemctl stop scope" in b and "systemctl start scope" in b),
}
NAMED = list(FIND)


def _others() -> dict[str, str]:
    """Blocks no name above claims (one added later): they must not close the shell either."""
    claimed = {b for key, wanted in FIND.values() for b in _blocks(_section(key)) if wanted(b)}
    return {f"{key}-{n}": b for key in SECTIONS
            for n, b in enumerate(_blocks(_section(key)), 1) if b not in claimed}


OTHERS = _others()
ALL = NAMED + list(OTHERS)
RESTARTERS = ["path-a", "path-b", "rollback-a", "rollback-b"]
HOW = pytest.mark.parametrize("how", ["straight", "nested"])
EVERY = pytest.mark.parametrize("name", ALL)
RESTARTS = pytest.mark.parametrize("name", RESTARTERS)


def block(name: str) -> str:
    if name in OTHERS:
        return OTHERS[name]
    key, wanted = FIND[name]
    found = [b for b in _blocks(_section(key)) if wanted(b)]
    assert len(found) == 1, f"{name}: {len(found)} blocks match in section {key}"
    return found[0]


STARTS = ("systemctl restart", "systemctl start")
PATHS = re.compile(r"/srv/scope|/etc/systemd/system|/etc/cron\.daily|/var/backups|/opt/uv/python|/tmp")

STUBS = {
    # a flag file in $BOX makes one step fail
    "git": 'case "$1" in\n'
           ' fetch) test ! -e "$BOX/fetch-fails"; exit;;\n'
           ' checkout) test ! -e "$BOX/checkout-fails"; exit;;\n'
           ' merge-base) test ! -e "$BOX/not-on-main"; exit;;\n'
           ' describe) echo v2099.01.01; exit;;\n'
           ' rev-parse) echo abc1234; exit;;\n'
           ' tag) printf "v2099.01.02\\nv2099.01.01\\n"; exit;;\n'
           "esac\nexit 0\n",
    "sqlite3": 'case "$2" in\n'
               ' .backup*) test ! -e "$BOX/backup-fails" || exit 1; p=${2#*\\\'}; p=${p%\\\'}; : > "$p";;\n'
               ' *integrity*) if [ -e "$BOX/integrity-bad" ]; then echo "*** in database main ***"; else echo ok; fi;;\n'
               ' *alembic*) echo 0a1b2c3d4e5f;;\n'
               "esac\nexit 0\n",
    "uv": 'test ! -e "$BOX/uv-fails"\n',
    "systemctl": "true\n",
    "cmp": "exit 1\n",  # every file differs, so every install step runs
    # a copy that works leaves the file, so the chmod after it finds it
    "cp": 'test ! -e "$BOX/cp-fails" || exit 1\nfor a; do :; done\ncase "$a" in */) ;; *) : > "$a";; esac\n',
    "chown": 'test ! -e "$BOX/chown-fails"\n',
    "python3": "true\n",
    "journalctl": "echo Application startup complete\n",
    "curl": "true\n",
}


def _find_bash() -> str | None:
    """bash on PATH, or the one Git for Windows keeps beside git."""
    found = [shutil.which("bash")]
    git = shutil.which("git")
    if git:
        found.append(str(Path(git).resolve().parents[1] / "bin" / "bash.exe"))
    for bash in found:
        if not bash or not Path(bash).exists():
            continue
        try:
            probe = subprocess.run([bash, "--noprofile", "--norc"], input=b"( exit 3 )\necho ran $?\n",
                                   capture_output=True, timeout=60, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.stdout.strip() == b"ran 3":
            return bash
    return None


BASH = _find_bash()
needs_bash = pytest.mark.skipif(BASH is None, reason="the probe found no bash that can run a block here")


class Box:
    """A temp dir standing in for the droplet, and one block run inside it."""

    def __init__(self, root: Path):
        self.root = root
        for d in ("bin", "tmp", "etc/systemd/system", "etc/cron.daily", "var/backups/scope",
                  "srv/scope/data", "srv/scope/deploy", "srv/scope/migrations/versions"):
            (root / d).mkdir(parents=True)
        for name, body in STUBS.items():
            self.write(f"bin/{name}", f'#!/usr/bin/env bash\necho "{name} ${{*//$BOX/}}" >> "$BOX/calls"\n{body}')
            (root / "bin" / name).chmod(0o755)
        self.write("srv/scope/data/scope.db", "live\n")
        self.write("srv/scope/migrations/versions/0001_made_up.py", "")
        self.write(RESTORE.lstrip("/"), "restore point\n")

    def write(self, path: str, text: str) -> None:
        (self.root / path).write_bytes(text.encode())

    def flag(self, *names: str) -> "Box":
        for name in names:
            self.write(name, "")
        return self

    @property
    def calls(self) -> list[str]:
        log = self.root / "calls"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def called(self, words: str) -> bool:
        return any(c.startswith(words) for c in self.calls)

    def index(self, words: str) -> int:
        assert self.called(words), f"{words!r} never ran: {self.calls}"
        return next(i for i, c in enumerate(self.calls) if c.startswith(words))

    @property
    def restarted(self) -> bool:
        return any(self.called(words) for words in STARTS)

    def run(self, name: str, how: str, wrong_window: bool = False) -> list[str]:
        """Paste block `name`, then one more line. Returns what the block printed.

        That next line must run in the shell the block was pasted into: a block that ends the
        shell either loses it or, nested, hands it to the parent."""
        text = block(name)
        text = re.sub(r"(?m)^(TAG|SHA)=[^\s;]*", f"\\1={TAG}", text)
        text = re.sub(r"(?m)^PREV=[^\s;]*", f"PREV={PREV}", text)
        text = re.sub(r"\bRP=(?!\S*\$\()[^\s;]*", f"RP={RESTORE}", text)
        text = PATHS.sub(lambda m: "$BOX" + m.group(0), text)
        if wrong_window:
            (self.root / "srv/scope/data/scope.db").unlink()
            shutil.rmtree(self.root / "srv/scope")
        paste = ('export BOX="$PWD" OUTER=$SHLVL; export PATH="$BOX/bin:$PATH"\n'
                 + ("bash --noprofile --norc\n" if how == "nested" else "")
                 + text + '\necho "NEXT depth=$((SHLVL - OUTER))"\n')
        done = subprocess.run([BASH, "--noprofile", "--norc"], input=paste.encode(), cwd=self.root,
                              capture_output=True, timeout=120, check=False, env=dict(os.environ))
        out = done.stdout.decode().splitlines()
        depth = 1 if how == "nested" else 0
        assert out and out[-1] == f"NEXT depth={depth}", \
            f"{name} ({how}): the line pasted after the block did not run in the shell it was pasted into: {out}"
        return out[:-1]

    def stops(self, name: str, how: str, never: tuple[str, ...] = ()) -> list[str]:
        """The block never reaches a command in `never`, and its last and only STOP line says so."""
        out = self.run(name, how)
        reached = [c for c in self.calls if c.startswith(never)] if never else []
        assert not reached, f"{name} ({how}): went on after the failure and ran {reached}"
        stop_lines = [line for line in out if line.startswith("STOP")]
        assert stop_lines and stop_lines == out[-1:], f"{name} ({how}): expected one STOP line, last: {out}"
        assert not any(line.startswith("DONE") for line in out), out
        return out


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


# ---------- the runbook still has the blocks these tests run ----------

@EVERY
def test_the_block_is_found_exactly_once(name):
    assert block(name)


# ---------- (d) nothing in a block can close the pasting shell ----------

@EVERY
def test_no_block_can_close_the_shell_it_is_pasted_into(name):
    b = block(name)
    whole = b.lstrip().startswith("(") and b.rstrip().endswith(")")
    assert whole or not re.search(r"\bexit\b|\bset\s+-\w*e", b), \
        f"{name}: an exit (or set -e) outside a ( ... ) subshell closes the pasting shell:\n{b}"


@needs_bash
@HOW
@EVERY
def test_a_block_pasted_where_there_is_no_scope_stops_and_the_shell_stays_open(box, name, how):
    out = box.run(name, how, wrong_window=True)
    stop_lines = [line for line in out if line.startswith("STOP")]
    assert len(out) == 1 and stop_lines == out and box.calls == [], (out, box.calls)


# ---------- (e) a line pasted after the block runs in the shell it was pasted into ----------

@needs_bash
@HOW
@EVERY
@pytest.mark.parametrize("failing", ["checkout-fails", "backup-fails", "fetch-fails"])
def test_the_next_pasted_line_runs_whether_the_block_succeeded_or_stopped(box, name, how, failing):
    box.flag(failing).run(name, how)


# ---------- (a) a failed checkout never reaches the restart ----------

@needs_bash
@HOW
@RESTARTS
def test_a_failed_checkout_prints_one_stop_and_never_restarts_or_starts(box, name, how):
    box.flag("checkout-fails").stops(name, how, never=STARTS + ("uv", "chown"))


# ---------- (b) a failed backup stops before the checkout ----------

@needs_bash
@HOW
@pytest.mark.parametrize("name", ["path-a", "path-b"])
def test_a_failed_backup_stops_before_the_checkout(box, name, how):
    box.flag("backup-fails").stops(name, how, never=STARTS + ("git checkout",))


@needs_bash
@HOW
def test_a_restore_point_that_fails_its_integrity_check_stops_before_the_checkout(box, how):
    box.flag("integrity-bad").stops("path-b", how, never=STARTS + ("git checkout",))


@needs_bash
@HOW
def test_a_failed_database_restore_stops_the_rollback_before_the_checkout(box, how):
    box.flag("cp-fails").stops("rollback-b", how, never=STARTS + ("git checkout",))


# ---------- (c) a failed uv sync stops before the restart ----------

@needs_bash
@HOW
@RESTARTS
def test_a_failed_uv_sync_stops_before_the_restart(box, name, how):
    box.flag("uv-fails").stops(name, how, never=STARTS + ("chown",))


@needs_bash
@HOW
@RESTARTS
def test_a_failed_chown_stops_before_the_restart(box, name, how):
    box.flag("chown-fails").stops(name, how, never=STARTS)


@needs_bash
@HOW
@pytest.mark.parametrize("name", ["path-a", "path-b", "rollback-a"])
def test_a_failed_unit_or_script_copy_stops_before_the_restart(box, name, how):
    box.flag("cp-fails").stops(name, how, never=STARTS)


# ---------- (f) the first production block refuses a tag that is not on origin/main ----------

@needs_bash
@HOW
def test_the_first_block_refuses_a_tag_that_is_not_on_origin_main(box, how):
    box.flag("not-on-main").stops("where", how, never=("git diff",))
    _on_main_check(box)


@needs_bash
@HOW
def test_the_first_block_checks_origin_main_after_fetching_it(box, how):
    out = box.run("where", how)
    assert not any(line.startswith("STOP") for line in out), out
    assert box.index("git fetch") < _on_main_check(box)


@needs_bash
@HOW
def test_a_failed_fetch_in_the_first_block_stops_before_anything_is_compared(box, how):
    box.flag("fetch-fails").stops("where", how, never=("git diff", "git merge-base"))


def _on_main_check(box: Box) -> int:
    """Where the block asked git whether the tag is on origin/main."""
    asked = [i for i, c in enumerate(box.calls)
             if re.fullmatch(rf"git merge-base --is-ancestor {re.escape(TAG)}(\^\{{commit\}})? origin/main", c)]
    assert asked, f"the block never asked whether {TAG} is on origin/main: {box.calls}"
    return asked[0]


# ---------- the blocks still do their work, in order, on a clean run ----------

@needs_bash
@HOW
@pytest.mark.parametrize("name, steps", [
    ("path-a", ["sqlite3", f"git checkout --quiet {TAG}", "uv sync", "chown", "systemctl restart scope"]),
    ("path-b", ["systemctl stop scope", "sqlite3", f"git checkout --quiet {TAG}", "uv sync", "chown",
                "systemctl start scope"]),
    ("rollback-a", [f"git checkout --quiet {PREV}", "uv sync", "chown", "systemctl restart scope"]),
    ("rollback-b", ["systemctl stop scope", "cp", f"git checkout --quiet {PREV}", "uv sync", "chown",
                    "systemctl start scope"]),
])
def test_a_clean_run_goes_through_its_steps_in_order(box, name, how, steps):
    out = box.run(name, how)
    assert not any(line.startswith("STOP") for line in out), out
    at = [box.index(s) for s in steps]
    assert at == sorted(at), (steps, box.calls)


@needs_bash
@HOW
@pytest.mark.parametrize("name", ["where", "check", "tags"])
def test_the_read_only_blocks_run_clean(box, name, how):
    out = box.run(name, how)
    assert not any(line.startswith("STOP") for line in out), out
    assert not box.restarted


@needs_bash
@HOW
@pytest.mark.parametrize("name", NAMED)
def test_a_clean_run_ends_in_done(box, name, how):
    out = box.run(name, how)
    assert out and out[-1].startswith("DONE"), f"{name} ({how}): a clean run must end in DONE <name>: {out}"
