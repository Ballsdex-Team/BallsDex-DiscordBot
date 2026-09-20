"""
Which other packages a quest type needs, and whether they are actually installed.

A quest counting auctions can only progress if the auction house package is installed and dispatching events. When
it isn't, nothing breaks: the quest simply never moves. That silence is the problem this module solves — the admin
shows the missing package next to the quest, `check_integrations` warns at startup, and `/pass diagnostics` lists
the whole picture, instead of leaving staff wondering why a tier never unlocks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.apps import apps

log = logging.getLogger("eventpass")


@dataclass(frozen=True)
class Integration:
    key: str
    label: str
    app_label: str
    note: str

    @property
    def installed(self) -> bool:
        return apps.is_installed(self.app_label)


AUCTION_HOUSE = Integration(
    "auction_house",
    "Buggy's auction house",
    "auction_house_app",
    "Listings, bids, the shop and direct sales all come from this package.",
)
BATTLES = Integration("battles", "Battles", "battle_app", "Battle results come from this package.")
PACKS = Integration("packs", "Packs", "pack_app", "Pack purchases come from this package.")
MERCHANT = Integration("merchant", "Merchant", "merchant_ext", "Merchant purchases come from this package.")
CRAFTING = Integration(
    "crafting", "Collectors (crafting)", "collector_ext", "Crafts are collector cards claimed with this package."
)

INTEGRATIONS: tuple[Integration, ...] = (AUCTION_HOUSE, BATTLES, PACKS, MERCHANT, CRAFTING)


def missing_integrations() -> list[Integration]:
    return [integration for integration in INTEGRATIONS if not integration.installed]


def check_integrations(quest_types: set[str] | None = None) -> list[str]:
    """
    The warnings to show: one per package that quests need but which isn't installed.

    Parameters
    ----------
    quest_types: set[str] | None
        Only warn about the packages these quest types need. Every package when left out.
    """
    from .types import TYPES

    warnings = []
    for integration in missing_integrations():
        types = [
            definition.type.label
            for definition in TYPES.values()
            if definition.integration is integration and (quest_types is None or definition.type in quest_types)
        ]
        if types:
            warnings.append(
                f"The {integration.label} package is not installed: quests of type "
                f"{', '.join(sorted(types))} will never progress."
            )
    return warnings


def log_integration_warnings(quest_types: set[str] | None = None):
    for warning in check_integrations(quest_types):
        log.warning(warning)
