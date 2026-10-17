"""Configuration, read from the environment. No secret has a default.

A default secret key is the kind of thing that works perfectly in development and
signs every session on the server with a value that is in the repository. There is
no default: a missing SCOPE_SECRET_KEY stops the app from starting, loudly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    file_store: Path
    secret_key: str
    production: bool

    @classmethod
    def from_env(cls) -> Settings:
        secret = os.environ.get("SCOPE_SECRET_KEY")
        if not secret:
            raise RuntimeError(
                "SCOPE_SECRET_KEY is not set. It signs session cookies, so there is no "
                "default: a default would mean every deployment shares a key that is "
                "in the repository."
            )
        return cls(
            database_url=os.environ.get("SCOPE_DB", "sqlite:///scope.db"),
            file_store=Path(os.environ.get("SCOPE_FILES", "./_files")),
            secret_key=secret,
            production=os.environ.get("SCOPE_PRODUCTION", "").lower() in ("1", "true", "yes"),
        )
