"""Moved out of tests/unit/api/test_hub_answers.py by TICKET-945, so that no test file imports another.
"""

from __future__ import annotations

from services.production.api import scope_facts as SF
from tests.helpers.scope_chapters import TRIPS as FORTY

CTX = SF.record_context(FORTY)
