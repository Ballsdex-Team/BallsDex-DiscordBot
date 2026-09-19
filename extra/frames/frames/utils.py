"""
Frames live in `Ball.capacity_logic`, one entry per day: "MM-DD-YYYY" for every treasure of the ball,
"MM-DD-YYYY:<special id>" for the treasures of that special only, and "MM-DD-YYYY:0" for the treasures without
special only.
"""

from __future__ import annotations

import random
import re
from datetime import date
from typing import Any

FRAME_KEY_RE = re.compile(r"^(\d{2}-\d{2}-\d{4})(?::(\d+))?$")
# in place of a special ID: the treasures without special
NO_SPECIAL = 0


def frame_key(day: date, special_id: int | None = None) -> str:
    """
    The key of a frame: for every treasure with `special_id` None, else for the treasures of that special, or
    without special with `NO_SPECIAL`.
    """
    key = day.strftime("%m-%d-%Y")
    return key if special_id is None else f"{key}:{special_id}"


def parse_frame_key(key: str) -> tuple[str, int | None] | None:
    """
    The date (MM-DD-YYYY) and the special ID of a frame key, None if it isn't a frame key.
    """
    match = FRAME_KEY_RE.match(key)
    if match is None:
        return None
    return match.group(1), None if match.group(2) is None else int(match.group(2))


def is_frame_entry(value: Any) -> bool:
    return isinstance(value, dict) and bool({"card", "spawn", "credits", "catch"} & value.keys())


def frames_depend_on_special(capacity_logic: Any, day: date) -> bool:
    """
    Whether some frames of this day only go to the treasures of a special, or to the treasures without special.
    """
    if not isinstance(capacity_logic, dict):
        return False
    prefix = frame_key(day) + ":"
    return any(key.startswith(prefix) and is_frame_entry(value) for key, value in capacity_logic.items())


def pick_frame(capacity_logic: Any, special_id: int | None, day: date) -> dict | None:
    """
    The frame a new treasure of this special, None without special, gets on this day: the frame of its special, or
    of the treasures without special, first, else the frame of every treasure. Each one is only given with its own
    chance.
    """
    if not isinstance(capacity_logic, dict):
        return None
    keys = [frame_key(day, NO_SPECIAL if special_id is None else special_id), frame_key(day)]
    for key in keys:
        entry = capacity_logic.get(key)
        if is_frame_entry(entry) and _roll(entry):
            return entry
    return None


def _roll(entry: dict) -> bool:
    chance = entry.get("chance", 100)
    return isinstance(chance, int) and 1 <= chance <= 100 and random.randint(1, 100) <= chance
