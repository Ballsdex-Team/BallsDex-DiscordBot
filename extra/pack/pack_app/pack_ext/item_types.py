from enum import StrEnum
from typing import TypedDict


class ItemType(StrEnum):
    Weapon = "weapon"
    Crew = "crew"
    Fruit = "fruit"
    Ship = "ship"


class Item(TypedDict):
    name: str
    rarity: int
    type: ItemType
