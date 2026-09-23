"""
Frames live in `Ball.capacity_logic`, under two kinds of key.

A **dated** frame is "MM-DD-YYYY" for every treasure of the ball, "MM-DD-YYYY:<special id>" for the treasures of
that special only, and "MM-DD-YYYY:0" for the treasures without special only. Those are the ones a catch can roll:
on its day, a new treasure may get the art.

A **named** frame is a plain slug, like "haki". It has no day, so nothing ever rolls it — it is only given on
purpose, as a pass reward or by an admin spawn. That is what makes it easy to point at: a reward asks for "haki"
rather than for "09-20-2026:3".

Both kinds can carry a `name`, the label players and staff read, and an `emoji` shown next to it. A dated frame
with a name can be handed out by that name too, so an event does not have to spell out a date.
"""

from __future__ import annotations

import random
import re
from datetime import date
from typing import Any

FRAME_KEY_RE = re.compile(r"^(\d{2}-\d{2}-\d{4})(?::(\d+))?$")
# a named frame: lowercase, no spaces, so it is easy to type in a reward
NAME_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
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


def slugify_frame_name(name: str) -> str:
    """
    The key a named frame is stored under: "Haki Aura" becomes "haki-aura".
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug[:32].rstrip("-")


def is_named_key(key: str) -> bool:
    """
    Whether this key is a named frame rather than a dated one.
    """
    return bool(NAME_KEY_RE.match(key)) and FRAME_KEY_RE.match(key) is None


def iter_frames(capacity_logic: Any):
    """
    Every frame stored on a treasure, as (key, entry) pairs, dated or named.
    """
    if not isinstance(capacity_logic, dict):
        return
    for key, value in capacity_logic.items():
        if is_frame_entry(value) and (parse_frame_key(key) is not None or is_named_key(key)):
            yield key, value


def frame_label(key: str, entry: dict) -> str:
    """
    What a frame is called: its name when it has one, else its key.
    """
    name = entry.get("name")
    return str(name) if name else key


def frame_mark(entry: dict | None, fallback: str = "") -> str:
    """
    The emoji and name shown next to a framed treasure, like "<:Haki:123> Haki".
    """
    if not isinstance(entry, dict):
        return fallback
    parts = [str(entry.get("emoji") or ""), str(entry.get("name") or fallback)]
    return " ".join(part for part in parts if part)


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
