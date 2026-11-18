"""TICKET-915: up to three questions a day, written from that day's own trades (RED stub)."""

from __future__ import annotations

from dataclasses import dataclass

MAX_QUESTIONS = 3


@dataclass(frozen=True)
class DayQuestion:
    key: str
    text: str


def questions_for(trades: list[dict]) -> list[DayQuestion]:
    """RED stub: the questions arrive in GREEN."""
    return []