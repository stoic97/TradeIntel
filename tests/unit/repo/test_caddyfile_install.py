"""TICKET-1016: a changed deploy/Caddyfile is installed by a person, before the deploy window.

Caddy serves production as well as staging, so no deploy script installs its config. The
runbook holds the one way to do it: validate the exact file the tag will carry, with staging's
credentials loaded the way systemd loads them, keep the old file, reload, check both sites at
once, and log it. A plain ``caddy validate`` in a root shell checks a different config (the
staging block reads its user and hash from the environment), so the runbook and the
first-install note both load the file first.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path("docs/runbooks/deploy.md").read_text(encoding="utf-8")
TRAIN = DEPLOY[DEPLOY.index("## The release train"):DEPLOY.index("## 6. Before the first partner uploads")]
STAGING_SCRIPT = Path("deploy/refresh-staging.sh").read_text(encoding="utf-8")
LOAD = "set -a; . /etc/caddy/staging-auth.env; set +a;"


def section() -> str:
    head = "### When `deploy/Caddyfile` changes"
    assert head in TRAIN, "no Caddyfile section in the release train"
    rest = TRAIN[TRAIN.index(head):]
    end = rest.find("\n### ", 1)
    return rest if end == -1 else rest[:end]


def test_the_install_is_by_hand_and_before_the_deploy_window():
    s = section()
    assert "never by `refresh-staging.sh`" in s
    assert "update.sh" not in s
    assert "before the deploy window" in s


def test_it_validates_the_tags_file_with_stagings_credentials_loaded():
    s = section()
    assert 'git show "$SHA:deploy/Caddyfile"' in s
    assert LOAD in s and "caddy validate" in s


def test_it_keeps_the_old_file_checks_both_sites_and_can_go_back():
    s = section()
    assert "Caddyfile.before-" in s
    assert "https://scope.plusev.in/health" in s
    assert "https://staging.scope.plusev.in/health" in s and "401" in s
    assert "systemctl reload caddy" in s


def test_it_is_logged():
    assert "docs/runbooks/deploys.md" in section()


def test_the_first_install_note_validates_with_the_credentials_loaded():
    validate = [line for line in STAGING_SCRIPT.splitlines() if "caddy validate" in line]
    assert validate and all(LOAD in line for line in validate), validate


# ---------- review, 24 Nov: what a paste must refuse ----------

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


def test_every_block_that_uses_sha_stops_when_it_is_unfilled():
    for block in _blocks(section()):
        if "$SHA" in block:
            assert 'test -n "$SHA" || stop "' in block, block


def test_a_failed_git_show_stops_the_paste_before_anything_is_validated():
    s = section()
    assert '> /tmp/Caddyfile.next || stop "' in s
    assert 'test -s /tmp/Caddyfile.next || stop "' in s


def test_the_bcrypt_hash_is_single_quoted_so_bash_reads_it_as_systemd_does():
    s = section()
    assert "grep -qx \"SCOPE_STAGING_HASH='[^'][^']*'\" /etc/caddy/staging-auth.env || stop" in s
    assert "SCOPE_STAGING_HASH='<hash>'" in STAGING_SCRIPT


def test_the_installed_file_is_validated_before_the_reload():
    s = section()
    live = "caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile ) && systemctl reload caddy"
    assert live in s


# ---------- TICKET-1048: what each block does, run in bash on made-up values ----------

SHA = "abc1234"
MADE_UP = "$2a$14$made.up.for.this.test"  # bcrypt's shape, no real hash
GOOD_AUTH = f"SCOPE_STAGING_USER=someone\nSCOPE_STAGING_HASH='{MADE_UP}'\n"
FETCH, INSTALL, PUT_BACK = 0, 1, 2
HOW = pytest.mark.parametrize("how", ["straight", "nested"])
BLOCKS = pytest.mark.parametrize("n", [FETCH, INSTALL, PUT_BACK], ids=["fetch", "install", "put-back"])

PATHS = re.compile(r"/tmp/Caddyfile\.next|/etc/caddy|/etc/systemd/system|/srv/scope")

STUBS = {
    # the tag's Caddyfile is $BOX/tag; a flag file in $BOX makes a step fail
    "git": 'if [ "$1" = fetch ]; then test ! -e "$BOX/fetch-fails"; exit; fi\n'
           'if [ -e "$BOX/show-fails" ]; then exit 128; fi\ncat "$BOX/tag"\n',
    # refuses without staging's hash exactly as written, and a config the test names
    "caddy": f"if [ \"$SCOPE_STAGING_HASH\" != '{MADE_UP}' ]; then exit 1; fi\n"
             'if [ ! -s "$3" ]; then exit 1; fi\n'
             'case "$3" in */Caddyfile.next) test ! -e "$BOX/refuse-next";; *) test ! -e "$BOX/refuse-live";; esac\n',
    "curl": "true\n",
    "systemctl": 'test ! -e "$BOX/reload-fails"\n',
    "install": 'cp "$3" "$4"\n',
    "sleep": "true\n",
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
        for d in ("bin", "etc/caddy", "etc/systemd/system/caddy.service.d", "srv/scope", "tmp"):
            (root / d).mkdir(parents=True)
        for name, body in STUBS.items():
            self.write(f"bin/{name}", f'#!/usr/bin/env bash\necho "{name} ${{*//$BOX/}}" >> "$BOX/calls"\n{body}')
            (root / "bin" / name).chmod(0o755)
        self.write("etc/systemd/system/caddy.service.d/staging-auth.conf", "[Service]\n")
        self.write("etc/caddy/staging-auth.env", GOOD_AUTH)
        self.write("etc/caddy/Caddyfile", "old\n")
        self.write("tag", "new\n")

    def write(self, path: str, text: str) -> None:
        (self.root / path).write_bytes(text.encode())

    def flag(self, name: str) -> None:
        self.write(name, "")

    def fetched(self) -> "Box":
        """As the first block leaves it."""
        self.write("tmp/Caddyfile.next", "new\n")
        self.write(f"etc/caddy/Caddyfile.before-{SHA}", "old\n")
        return self

    @property
    def live(self) -> str:
        return (self.root / "etc/caddy/Caddyfile").read_text(encoding="utf-8")

    @property
    def calls(self) -> list[str]:
        log = self.root / "calls"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def called(self, words: str) -> bool:
        return any(c.startswith(words) for c in self.calls)

    def run(self, n: int, how: str, sha: str = SHA) -> list[str]:
        """Paste block n, then one more line. Returns what the block printed.

        That next line must run in the shell the block was pasted into: a stop that ends
        the shell either loses it or, nested, hands it to the parent."""
        blocks = _blocks(section())
        assert len(blocks) == 3, len(blocks)
        block, filled = re.subn(r"^SHA=$", f"SHA={sha}", blocks[n], flags=re.MULTILINE)
        assert filled == 1, block
        block = PATHS.sub(lambda m: "$BOX" + m.group(0), block)
        paste = ('export BOX="$PWD" OUTER=$SHLVL; export PATH="$BOX/bin:$PATH"\n'
                 + ("bash --noprofile --norc\n" if how == "nested" else "")
                 + block + '\necho "NEXT depth=$((SHLVL - OUTER))"\n')
        done = subprocess.run([BASH, "--noprofile", "--norc"], input=paste.encode(), cwd=self.root,
                              capture_output=True, timeout=120, check=False, env=dict(os.environ))
        out = done.stdout.decode().splitlines()
        depth = 1 if how == "nested" else 0
        assert out and out[-1] == f"NEXT depth={depth}", (out, done.stderr.decode())
        return out[:-1]

    def stops(self, n: int, how: str, why: str, sha: str = SHA) -> list[str]:
        """Block n stops: its last line, and its only STOP line, says why."""
        out = self.run(n, how, sha)
        assert out and [line for line in out if line.startswith("STOP")] == out[-1:], out
        assert why in out[-1], out
        return out


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


@needs_bash
@HOW
@BLOCKS
def test_an_empty_sha_stops_every_block_before_it_does_anything(box, n, how):
    out = box.fetched().stops(n, how, "SHA= is empty", sha="")
    assert len(out) == 1 and box.calls == [] and box.live == "old\n"


@needs_bash
@HOW
@BLOCKS
def test_a_block_pasted_where_there_is_no_scope_stops(box, n, how):
    (box.root / "srv/scope").rmdir()
    out = box.fetched().stops(n, how, "/srv/scope")
    assert len(out) == 1 and box.calls == [] and box.live == "old\n"


@needs_bash
@HOW
@pytest.mark.parametrize("flag, why", [("fetch-fails", "git fetch failed"), ("show-fails", "git show failed")])
def test_a_failed_fetch_or_show_says_so_and_nothing_is_validated(box, how, flag, why):
    box.flag(flag)
    box.stops(FETCH, how, why)
    assert not box.called("caddy")
    assert not (box.root / f"etc/caddy/Caddyfile.before-{SHA}").exists()


@needs_bash
@HOW
def test_an_empty_fetched_file_says_so_and_nothing_is_validated(box, how):
    box.write("tag", "")
    box.stops(FETCH, how, "empty")
    assert not box.called("caddy")
    assert not (box.root / f"etc/caddy/Caddyfile.before-{SHA}").exists()


BAD_AUTH = {
    "no-closing-quote": f"SCOPE_STAGING_HASH='{MADE_UP}\n",
    "unquoted": f"SCOPE_STAGING_HASH={MADE_UP}\n",
    "double-quoted": f'SCOPE_STAGING_HASH="{MADE_UP}"\n',
    "empty-quotes": "SCOPE_STAGING_HASH=''\n",
    "second-unquoted-below": GOOD_AUTH + f"SCOPE_STAGING_HASH={MADE_UP}\n",
    "second-exported-below": GOOD_AUTH + f"export SCOPE_STAGING_HASH={MADE_UP}\n",
    "second-quoted-below": GOOD_AUTH + f"SCOPE_STAGING_HASH='{MADE_UP}'\n",
    "none": "SCOPE_STAGING_USER=someone\n",
}


@needs_bash
@HOW
@pytest.mark.parametrize("auth", BAD_AUTH.values(), ids=BAD_AUTH.keys())
def test_anything_but_one_quoted_hash_line_is_refused_and_never_printed(box, how, auth):
    box.write("etc/caddy/staging-auth.env", auth)
    out = box.stops(FETCH, how, "SCOPE_STAGING_HASH")
    assert not box.called("caddy")
    assert "made.up" not in "\n".join(out)


@needs_bash
@HOW
@pytest.mark.parametrize("gone", ["etc/caddy/staging-auth.env",
                                  "etc/systemd/system/caddy.service.d/staging-auth.conf"])
def test_missing_staging_auth_stops(box, how, gone):
    (box.root / gone).unlink()
    out = box.stops(FETCH, how, "staging auth is missing")
    assert "staging auth: present" not in out and not box.called("caddy")


@needs_bash
@HOW
def test_a_config_caddy_refuses_never_prints_valid(box, how):
    box.flag("refuse-next")
    out = box.stops(FETCH, how, "caddy refused")
    assert "VALID" not in out and box.live == "old\n"


@needs_bash
@HOW
def test_the_first_block_passes_a_good_file_and_changes_nothing_live(box, how):
    out = box.run(FETCH, how)
    assert out[-2:] == ["staging auth: present", "VALID"]
    assert box.live == "old\n"
    assert (box.root / f"etc/caddy/Caddyfile.before-{SHA}").read_text(encoding="utf-8") == "old\n"
    assert not box.called("install") and not box.called("systemctl")


@needs_bash
@HOW
def test_two_empty_files_never_match(box, how):
    box.fetched().write("tag", "")
    box.write("tmp/Caddyfile.next", "")
    out = box.stops(INSTALL, how, "empty")
    assert not any("matches" in line for line in out)
    assert not box.called("install") and box.live == "old\n"


@needs_bash
@HOW
def test_a_file_that_is_not_the_one_at_the_sha_is_not_installed(box, how):
    box.fetched().write("tmp/Caddyfile.next", "another train's\n")
    box.stops(INSTALL, how, f"not the file at {SHA}")
    assert not box.called("install") and box.live == "old\n"


@needs_bash
@HOW
def test_a_failed_git_show_in_the_second_block_installs_nothing(box, how):
    box.fetched().flag("show-fails")
    box.stops(INSTALL, how, "nothing was installed")
    assert not box.called("install") and box.live == "old\n"


@needs_bash
@HOW
def test_nothing_is_installed_without_a_saved_copy_to_go_back_to(box, how):
    (box.fetched().root / f"etc/caddy/Caddyfile.before-{SHA}").unlink()
    box.stops(INSTALL, how, "no saved copy")
    assert not box.called("install") and box.live == "old\n"


@needs_bash
@HOW
def test_a_refused_file_never_reaches_the_live_path(box, how):
    box.fetched().flag("refuse-next")
    box.stops(INSTALL, how, "nothing was installed")
    assert box.live == "old\n"
    assert not box.called("install") and not box.called("systemctl")


@needs_bash
@HOW
def test_a_file_refused_once_live_is_taken_back_and_not_reloaded(box, how):
    box.fetched().flag("refuse-live")
    box.stops(INSTALL, how, "the saved copy is back")
    assert box.live == "old\n" and not box.called("systemctl")


@needs_bash
@HOW
def test_a_failed_reload_takes_the_file_back(box, how):
    box.fetched().flag("reload-fails")
    box.stops(INSTALL, how, "the saved copy is back")
    assert box.live == "old\n" and not box.called("curl")


@needs_bash
@HOW
def test_the_second_block_validates_right_before_it_installs_then_reloads(box, how):
    out = box.fetched().run(INSTALL, how)
    assert f"matches {SHA}" in out and not any(line.startswith("STOP") for line in out)
    assert box.live == "new\n"
    steps = [c for c in box.calls if c.split()[0] in ("caddy", "install", "systemctl")]
    assert steps == [
        "caddy validate --config /tmp/Caddyfile.next --adapter caddyfile",
        "install -m 644 /tmp/Caddyfile.next /etc/caddy/Caddyfile",
        "caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile",
        "systemctl reload caddy",
    ]


@needs_bash
@HOW
def test_putting_back_without_a_saved_copy_stops(box, how):
    box.write("etc/caddy/Caddyfile", "new\n")
    box.stops(PUT_BACK, how, "no saved copy")
    assert box.live == "new\n" and box.calls == []


@needs_bash
@HOW
def test_putting_back_says_when_caddy_did_not_reload(box, how):
    box.fetched().flag("reload-fails")
    box.write("etc/caddy/Caddyfile", "new\n")
    box.stops(PUT_BACK, how, "did not reload")
    assert box.live == "old\n"


@needs_bash
@HOW
def test_putting_back_restores_the_saved_copy_and_reloads(box, how):
    box.fetched().write("etc/caddy/Caddyfile", "new\n")
    box.run(PUT_BACK, how)
    assert box.live == "old\n" and box.calls == ["systemctl reload caddy"]
