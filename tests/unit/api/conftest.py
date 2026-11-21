"""Fixtures every test in tests/unit/api gets without importing them (TICKET-945).

They lived in test_upload.py and were imported by name into other test files, which is how a
fixture of the same name gets silently replaced. A test file that needs a different one
defines its own, and that one wins.
"""

import pytest

from tests.helpers.upload import upload_client, upload_engine


@pytest.fixture()
def engine():
    return upload_engine()


@pytest.fixture()
def client(engine):
    return upload_client(engine)
