"""Plain helpers and constants that test files share (TICKET-945).

A test file never imports from another test file: what two of them share lives here.
Fixtures stay in a conftest.py or in the test file that uses them.
"""
