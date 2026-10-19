"""Raw files: stored once, named by their plaintext hash, encrypted at rest.

Methodology Rule 1 says a raw export is stored once, hashed at ingestion and never
modified. ADR 007 adds encryption at rest. Two details follow from putting those
together, and both matter:

**The name is the hash of the plaintext.** It has to identify the file the trader
sent, so that an import record's sha256 means "this is what he gave us" and stays
true if the ciphertext is ever rewritten with a new key. Hashing the ciphertext
would tie the identity of his file to our key, which is backwards.

**Storing is idempotent.** The same content lands at the same path, so a re-upload
of a byte-identical file does not make a second copy. The import layer still refuses
it with a message -- the store simply does not duplicate.

Fernet (AES-128-CBC with an HMAC) is the choice because it authenticates: a wrong
key or a modified file raises rather than returning plausible-looking bytes. An
unauthenticated cipher would let a corrupted file decrypt to garbage that the parser
would then reject as a bad export, blaming the trader for our disk.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class CannotDecrypt(Exception):
    """The key does not open this file, or the file has been altered."""


class NoSuchFile(Exception):
    """No stored file with that hash."""


def generate_key() -> str:
    """A new key, for a new deployment. Kept outside the repo and outside backups."""
    return Fernet.generate_key().decode()


@dataclass(frozen=True)
class StoredFile:
    sha256: str
    path: Path
    size: int


class FileStore:
    """Content-addressed, encrypted storage for raw broker exports."""

    def __init__(self, root: Path, key: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def _path_for(self, sha256: str) -> Path:
        return self.root / f"{sha256}.enc"

    def put(self, content: bytes) -> StoredFile:
        digest = hashlib.sha256(content).hexdigest()
        path = self._path_for(digest)
        if not path.exists():
            path.write_bytes(self._fernet.encrypt(content))
            path.chmod(0o600)
        return StoredFile(sha256=digest, path=path, size=len(content))

    def get(self, sha256: str) -> bytes:
        path = self._path_for(sha256)
        if not path.exists():
            raise NoSuchFile(f"no stored file {sha256}")
        try:
            return self._fernet.decrypt(path.read_bytes())
        except InvalidToken as exc:
            raise CannotDecrypt(
                f"{sha256} could not be decrypted: wrong key, or the file has been "
                "altered. Fernet authenticates, so this is a refusal rather than "
                "garbage that would later be blamed on the trader's export."
            ) from exc

    def delete(self, sha256: str) -> Path | None:
        """Remove one file. Returns its path, or None if it was already gone."""
        path = self._path_for(sha256)
        if not path.exists():
            return None
        path.unlink()
        return path

    def exists(self, sha256: str) -> bool:
        return self._path_for(sha256).exists()
