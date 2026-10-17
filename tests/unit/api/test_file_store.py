"""Raw files: stored once, hashed, encrypted at rest (methodology Rule 1, ADR 007).

The hash is over the **plaintext**, because it has to identify the file the trader
sent -- a hash of the ciphertext would change if we ever re-encrypted and would not
match what the import record claims. The ciphertext is just the storage form.

Encryption is here rather than in deployment because a file that lands unencrypted
in development is a file someone eventually copies to a server.
"""

from __future__ import annotations

import hashlib

import pytest

from services.production.accounts import file_store as fs

CONTENT = b"Date,Time,Name\n2026-10-16,10:15:03,WIDGETOIL 19 NOV 5000 CALL\n"
KEY = fs.generate_key()


@pytest.fixture()
def store(tmp_path):
    return fs.FileStore(root=tmp_path / "files", key=KEY)


def test_what_lands_on_disk_is_not_the_file(store):
    stored = store.put(CONTENT)
    on_disk = stored.path.read_bytes()
    assert CONTENT not in on_disk
    assert b"WIDGETOIL" not in on_disk


def test_it_round_trips_exactly(store):
    stored = store.put(CONTENT)
    assert store.get(stored.sha256) == CONTENT


def test_the_name_is_the_hash_of_the_plaintext(store):
    stored = store.put(CONTENT)
    assert stored.sha256 == hashlib.sha256(CONTENT).hexdigest()
    assert stored.sha256 in str(stored.path)


def test_storing_the_same_content_twice_is_one_file(store):
    first = store.put(CONTENT)
    second = store.put(CONTENT)
    assert first.sha256 == second.sha256
    assert first.path == second.path
    assert len(list(store.root.iterdir())) == 1


def test_a_wrong_key_fails_loudly(store, tmp_path):
    stored = store.put(CONTENT)
    other = fs.FileStore(root=store.root, key=fs.generate_key())
    with pytest.raises(fs.CannotDecrypt):
        other.get(stored.sha256)


def test_a_missing_file_is_a_named_error(store):
    with pytest.raises(fs.NoSuchFile):
        store.get("0" * 64)


def test_delete_removes_the_file_and_says_so(store):
    stored = store.put(CONTENT)
    assert store.delete(stored.sha256) == stored.path
    assert not stored.path.exists()
    assert store.delete(stored.sha256) is None, "deleting twice is not an error"


def test_the_key_comes_from_settings_and_has_no_default(monkeypatch):
    monkeypatch.delenv("SCOPE_FILE_KEY", raising=False)
    monkeypatch.setenv("SCOPE_SECRET_KEY", "x" * 32)
    from services.production.api import settings as st
    with pytest.raises(RuntimeError, match="SCOPE_FILE_KEY"):
        st.Settings.from_env()
