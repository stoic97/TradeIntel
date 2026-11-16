"""Moved out of tests/unit/mirror/test_page.py by TICKET-945, so that no test file imports another.
"""

from __future__ import annotations

# Words the product never uses, from PRD 7.5 and the Workbook's never-use list.
# These are claims by their nature: there is no sentence in which the product may
# call a trader's behaviour tilt or name his edge.
NEVER_USED = [
    "tilt",
    "revenge",
    "emotional",
    "psychology",
    "disease",
    "cure",
    "edge",
    "alpha",
    "expectancy",
    "discipline",
    "mistake",
    "should have",
]
