"""
Build an event pass from a plain description of it, so a whole event can be written, reviewed and loaded at once
instead of being clicked together in the admin. The `load_event_pass` command reads that description from a JSON file.

Everything is matched by name: the pass, its tiers and quests, and the treasures, specials, packs or craft types they
point at. Loading the same description again updates the pass in place, which is how a draft gets corrected. A pass
that isn't a draft anymore is never touched: players may already be on it.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from collector_app.models import Collector, CollectorTierLevel
from currency_app.models import Item
from django.db import models
from django.utils.dateparse import parse_datetime
from merchant_app.models import MerchantItem

from ballsdex.core.game_events import normalize_command
from bd_models.models import Ball, BallGroup, Economy, Regime, Special

from .models import (
    AccessKind,
    Announce,
    BonusMode,
    EventPass,
    Logic,
    PassRequirement,
    PassTier,
    Quest,
    QuestType,
    RequirementKind,
    Reset,
    Reward,
    RewardKind,
    RewardLine,
    RewardMode,
    TierRequirement,
)
from .types import PARAMETER_FIELDS, TYPES

PASS_KEYS = {
    "name",
    "emoji",
    "description",
    "colour",
    "starts_at",
    "ends_at",
    "claim_until",
    "main_server_id",
    "main_server_only",
    "final_reward",
    "final_message",
    "position",
    "notes",
    "token",
    "card_special",
    "access",
    "access_logic",
    "access_message",
    "tiers",
}
ACCESS_KEYS = {
    "role": AccessKind.ROLE,
    "max_treasures": AccessKind.MAX_TREASURES,
    "min_treasures": AccessKind.MIN_TREASURES,
    "max_berries": AccessKind.MAX_CURRENCY,
    "min_berries": AccessKind.MIN_CURRENCY,
}
TIER_KEYS = {"name", "emoji", "description", "locked_message", "unlock_logic", "reward", "requirements", "quests"}
QUEST_KEYS = {
    "name",
    "emoji",
    "description",
    "type",
    "goal",
    "measure",
    "reset",
    "mandatory",
    "hidden",
    "enabled",
    "claim_required",
    "announce",
    "completion_message",
    "starts_at",
    "ends_at",
    "notes",
    "reward",
}
REWARD_KEYS = {"cards", "tokens", "berries", "mode", "pick", "offer", "pool"}
POOL_KEYS = {"group", "regime", "economy", "min_rarity", "max_rarity", "exclude", "quantity"}

# quest settings whose name in the file differs from the model field
ALIASES = {"partner": "partner_discord_id", "command": "command_name", "craft_type": "tier_level"}
FILTER_NAMES = set(PARAMETER_FIELDS) | set(ALIASES)


class PassLoader:
    """
    Loads one pass. Every problem is collected in `errors` instead of stopping at the first one, so a file can be
    fixed in one go: the caller rolls everything back when there is any.
    """

    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.errors: list[str] = []
        self.report: list[str] = []
        self.event_pass: EventPass | None = None
        self.token: Ball | None = None
        self.card_special: Special | None = None
        self._tokens: defaultdict[str, int] = defaultdict(int)

    # -- lookups -----------------------------------------------------------------------------------------------------

    def _missing(self, what: str, name: object) -> None:
        self.errors.append(f'No {what} named "{name}".')

    def _ball(self, name: str) -> Ball | None:
        ball = Ball.objects.filter(country=name).first()
        if ball is None:
            self._missing("treasure", name)
        return ball

    def _special(self, name: str) -> Special | None:
        special = Special.objects.filter(name=name).first()
        if special is None:
            self._missing("special", name)
        return special

    def _item(self, name: str) -> Item | None:
        # pack names often end with an emoji: "Gold Pack" finds "Gold Pack 🥇", as long as it is the only match
        item = Item.objects.filter(name=name).first()
        if item is None:
            matches = list(Item.objects.filter(name__istartswith=name)[:2])
            item = matches[0] if len(matches) == 1 else None
        if item is None:
            self._missing("pack", name)
        return item

    def _by_name(self, model: type[models.Model], what: str, name: str) -> models.Model | None:
        found = model.objects.filter(name=name).first()
        if found is None:
            self._missing(what, name)
        return found

    def _date(self, value: str | None, where: str) -> datetime | None:
        if value is None:
            return None
        parsed = parse_datetime(value)
        if parsed is None or parsed.tzinfo is None:
            self.errors.append(f'{where}: "{value}" is not a date with a timezone, like "2026-10-09T00:01:00Z".')
            return None
        return parsed

    def _check_keys(self, data: dict[str, Any], allowed: set[str], where: str) -> None:
        unknown = sorted(set(data) - allowed)
        if unknown:
            self.errors.append(f"{where}: unknown setting(s) {', '.join(unknown)}.")

    # -- building ----------------------------------------------------------------------------------------------------

    def load(self) -> EventPass | None:
        data = self.data
        name = data.get("name")
        if not name:
            self.errors.append("The pass needs a name.")
            return None
        self._check_keys(data, PASS_KEYS, "The pass")
        existing = EventPass.objects.filter(name=name).first()
        if existing and existing.status != EventPass.Status.DRAFT:
            self.errors.append(
                f'"{name}" is {existing.get_status_display().lower()}, players may already be on it: move it back to '
                "draft in the admin to load it again."
            )
            return None
        if data.get("token"):
            self.token = self._ball(data["token"])
        if data.get("card_special"):
            self.card_special = self._special(data["card_special"])

        dates = {key: self._date(data.get(key), "The pass") for key in ("starts_at", "ends_at", "claim_until")}
        for key in ("starts_at", "ends_at"):
            if not data.get(key):
                self.errors.append(f"The pass needs {key}.")
        if dates["starts_at"] is None or dates["ends_at"] is None:
            # the pass can't even be saved without its dates, the rest of the file is checked once they are fixed
            return None
        if dates["ends_at"] <= dates["starts_at"]:
            self.errors.append("The pass must end after it starts.")

        # a new pass is always created as a draft, and an existing one keeps its status
        event_pass, created = EventPass.objects.update_or_create(
            name=name,
            defaults={
                "emoji": data.get("emoji", ""),
                "description": data.get("description", ""),
                "colour": data.get("colour", ""),
                **dates,
                "main_server_id": data.get("main_server_id"),
                "main_server_only": data.get("main_server_only", False),
                "final_message": data.get("final_message", ""),
                "position": data.get("position", 0),
                "notes": data.get("notes", ""),
            },
        )
        self.event_pass = event_pass
        self._access(event_pass, data)
        final = data.get("final_reward")
        event_pass.final_reward = self._reward(f"{name} · final reward", final, None) if final else None
        event_pass.save(update_fields=("final_reward",))
        self.report.append(f"{'Created' if created else 'Updated'} {event_pass}.")

        for position, tier_data in enumerate(data.get("tiers", []), start=1):
            self._tier(event_pass, position, tier_data)

        token_lines = [f"{tier} {count}" for tier, count in self._tokens.items()]
        if token_lines:
            self.report.append(f"Tokens given: {', '.join(token_lines)} ({sum(self._tokens.values())} in total).")
        return event_pass

    def _tier(self, event_pass: EventPass, position: int, data: dict[str, Any]) -> None:
        name = data.get("name", "")
        where = f'Tier "{name}"'
        self._check_keys(data, TIER_KEYS, where)
        logic = data.get("unlock_logic", Logic.ALL)
        if logic not in Logic.values:
            self.errors.append(f"{where}: the unlock logic is one of {', '.join(Logic.values)}.")
        tier, _ = PassTier.objects.update_or_create(
            event_pass=event_pass,
            name=name,
            defaults={
                "emoji": data.get("emoji", ""),
                "description": data.get("description", ""),
                "position": position,
                "unlock_logic": logic,
                "locked_message": data.get("locked_message", ""),
                "reward": (
                    self._reward(f"{event_pass.name} · {name} (tier reward)", data["reward"], None)
                    if data.get("reward")
                    else None
                ),
            },
        )
        quests = [
            self._quest(event_pass, tier, index, quest_data)
            for index, quest_data in enumerate(data.get("quests", []), start=1)
        ]
        tier.requirements.all().delete()
        for requirement in data.get("requirements", []):
            self._requirement(tier, requirement, where)

        loaded = [quest for quest in quests if quest is not None]
        mandatory = sum(1 for quest in loaded if quest.mandatory)
        hidden = sum(1 for quest in loaded if quest.hidden)
        self.report.append(
            f"  {tier.emoji} {tier.name}: {len(loaded)} quests ({mandatory} mandatory, {hidden} secret), "
            f"{len(data.get('requirements', []))} unlock requirement(s)."
        )

    def _requirement(self, tier: PassTier, spec: str | dict[str, Any], where: str) -> None:
        if spec == "finish_previous":
            TierRequirement.objects.create(tier=tier, kind=RequirementKind.FINISH_PREVIOUS)
            return
        if spec == "previous_tier":
            TierRequirement.objects.create(tier=tier, kind=RequirementKind.PREVIOUS_TIER)
            return
        if not isinstance(spec, dict) or len(spec) != 1:
            self.errors.append(f"{where}: unknown requirement {spec!r}.")
            return
        ((kind, value),) = spec.items()
        match kind:
            case "date":
                TierRequirement.objects.create(tier=tier, kind=RequirementKind.DATE, date=self._date(value, where))
            case "quests_count":
                TierRequirement.objects.create(tier=tier, kind=RequirementKind.QUESTS_COUNT, count=value)
            case "berries":
                TierRequirement.objects.create(tier=tier, kind=RequirementKind.CURRENCY, count=value)
            case "own":
                TierRequirement.objects.create(
                    tier=tier,
                    kind=RequirementKind.OWN_TREASURES,
                    count=value.get("count", 1),
                    ball=self._ball(value["ball"]) if value.get("ball") else None,
                    special=self._special(value["special"]) if value.get("special") else None,
                )
            case "quests":
                requirement = TierRequirement.objects.create(tier=tier, kind=RequirementKind.QUESTS_ALL)
                found = list(Quest.objects.filter(event_pass=tier.event_pass, name__in=value))
                for missing in sorted(set(value) - {quest.name for quest in found}):
                    self._missing("quest", missing)
                requirement.quests.set(found)
            case _:
                self.errors.append(f"{where}: unknown requirement {kind!r}.")

    def _quest(self, event_pass: EventPass, tier: PassTier, position: int, data: dict[str, Any]) -> Quest | None:
        name = data.get("name", "")
        where = f'Quest "{name}"'
        quest_type = data.get("type")
        if quest_type not in QuestType.values:
            self.errors.append(f"{where}: unknown type {quest_type!r}.")
            return None
        definition = TYPES[quest_type]
        self._check_keys(data, QUEST_KEYS | FILTER_NAMES, where)

        # every filter starts from its default, so one removed from the file is also removed from the quest
        fields: dict[str, Any] = {}
        for field_name in PARAMETER_FIELDS:
            model_field = Quest._meta.get_field(field_name)
            fields[field_name] = None if model_field.null else model_field.get_default()
        for key, value in data.items():
            field_name = ALIASES.get(key, key)
            if field_name not in PARAMETER_FIELDS:
                continue
            if field_name not in definition.fields:
                self.errors.append(f'{where}: a "{definition.type.label}" quest has no "{key}" setting.')
                continue
            fields[field_name] = self._filter_value(field_name, value)

        measure = data.get("measure", definition.measures[0])
        if measure not in definition.measures:
            self.errors.append(f"{where}: this type measures {' or '.join(definition.measures)}.")
        for key, choices in (("reset", Reset), ("announce", Announce)):
            if key in data and data[key] not in choices.values:
                self.errors.append(f"{where}: {key} is one of {', '.join(choices.values)}.")

        hidden = data.get("hidden", False)
        reward_spec = data.get("reward")
        tokens_counted_in = f"{tier.name}{' secret' if hidden else ''}"
        fields.update(
            {
                "tier": tier,
                "position": position,
                "description": data.get("description", ""),
                "emoji": data.get("emoji", ""),
                "type": quest_type,
                "target": data.get("goal", 1),
                "measure": measure,
                "reset": data.get("reset", Reset.NONE),
                "mandatory": data.get("mandatory", False),
                "hidden": hidden,
                "enabled": data.get("enabled", True),
                "claim_required": data.get("claim_required", True),
                "announce": data.get("announce", Announce.PUBLIC),
                "completion_message": data.get("completion_message", ""),
                "starts_at": self._date(data.get("starts_at"), where),
                "ends_at": self._date(data.get("ends_at"), where),
                "notes": data.get("notes", ""),
                "reward": (
                    self._reward(f"{event_pass.name} · {name}", reward_spec, tokens_counted_in) if reward_spec else None
                ),
            }
        )
        quest, _ = Quest.objects.update_or_create(event_pass=event_pass, name=name, defaults=fields)
        return quest

    def _filter_value(self, field_name: str, value: Any) -> Any:
        match field_name:
            case "ball":
                return self._ball(value)
            case "special":
                return self._special(value)
            case "group":
                return self._by_name(BallGroup, "group", value)
            case "item":
                return self._item(value)
            case "merchant_item":
                return self._by_name(MerchantItem, "merchant item", value)
            case "collector":
                return self._by_name(Collector, "collector", value)
            case "tier_level":
                return self._by_name(CollectorTierLevel, "craft type", value)
            case "command_name":
                return normalize_command(value)
        return value

    def _access(self, event_pass: EventPass, data: dict[str, Any]) -> None:
        """
        Who is allowed on the pass. No condition at all leaves it open to everyone.
        """
        logic = data.get("access_logic", Logic.ALL)
        if logic not in Logic.values:
            self.errors.append(f"The pass: the access logic is one of {', '.join(Logic.values)}.")
            logic = Logic.ALL
        EventPass.objects.filter(pk=event_pass.pk).update(
            access_logic=logic, access_message=data.get("access_message", "")
        )
        event_pass.access_logic, event_pass.access_message = logic, data.get("access_message", "")
        event_pass.access.all().delete()
        for spec in data.get("access", []):
            if not isinstance(spec, dict) or len(spec) not in (1, 2):
                self.errors.append(f"The pass: unknown access condition {spec!r}.")
                continue
            name = next((key for key in spec if key in ACCESS_KEYS), None)
            if name is None:
                self.errors.append(
                    f"The pass: an access condition is one of {', '.join(sorted(ACCESS_KEYS))}, not {sorted(spec)}."
                )
                continue
            value = spec[name]
            kind = ACCESS_KEYS[name]
            PassRequirement.objects.create(
                event_pass=event_pass,
                kind=kind,
                role_id=value if kind == AccessKind.ROLE else None,
                role_name=spec.get("role_name", ""),
                count=0 if kind == AccessKind.ROLE else value,
            )
        count = len(data.get("access", []))
        if count:
            self.report.append(f"  Reserved to players meeting {count} condition(s) ({logic}).")

    def _pool_line(self, reward: Reward, spec: dict[str, Any], name: str) -> RewardLine | None:
        """
        A line that draws its treasure from a pool instead of naming one.
        """
        self._check_keys(spec, POOL_KEYS, f'Pool of reward "{name}"')
        line = RewardLine(
            reward=reward,
            kind=RewardKind.TREASURE,
            special=self.card_special,
            bonus_mode=BonusMode.RANDOM,
            quantity=spec.get("quantity", 1),
            group=self._by_name(BallGroup, "group", spec["group"]) if spec.get("group") else None,
            regime=self._by_name(Regime, "regime", spec["regime"]) if spec.get("regime") else None,
            economy=self._by_name(Economy, "economy", spec["economy"]) if spec.get("economy") else None,
            min_rarity=spec.get("min_rarity"),
            max_rarity=spec.get("max_rarity"),
        )
        if not any(
            (line.group_id, line.regime_id, line.economy_id, line.min_rarity is not None, line.max_rarity is not None)
        ):
            self.errors.append(
                f'Reward "{name}": a pool needs at least a group, a regime, an economy or a rarity bound.'
            )
            return None
        return line

    def _reward(self, name: str, spec: dict[str, Any], counted_in: str | None) -> Reward:
        self._check_keys(spec, REWARD_KEYS, f'Reward "{name}"')
        mode = spec.get("mode", RewardMode.ALL)
        if mode not in RewardMode.values:
            self.errors.append(f'Reward "{name}": the mode is one of {", ".join(RewardMode.values)}.')
            mode = RewardMode.ALL
        reward, _ = Reward.objects.update_or_create(
            name=name[:64], defaults={"mode": mode, "pick": spec.get("pick", 1), "offer": spec.get("offer", 0)}
        )
        reward.lines.all().delete()
        lines = [
            RewardLine(
                reward=reward,
                kind=RewardKind.TREASURE,
                ball=self._ball(card),
                special=self.card_special,
                bonus_mode=BonusMode.RANDOM,
            )
            for card in spec.get("cards", [])
        ]
        pools = spec.get("pool")
        for pool_spec in [pools] if isinstance(pools, dict) else (pools or []):
            pool_line = self._pool_line(reward, pool_spec, name)
            if pool_line is not None:
                lines.append(pool_line)
        if tokens := spec.get("tokens", 0):
            if self.token is None:
                self.errors.append(f'Reward "{name}" gives tokens, but the pass names no "token" treasure.')
            # the token's own settings decide whether it can be traded or sold, not the reward
            lines.append(
                RewardLine(
                    reward=reward, kind=RewardKind.TREASURE, ball=self.token, quantity=tokens, bonus_mode=BonusMode.ZERO
                )
            )
            if counted_in:
                self._tokens[counted_in] += tokens
        if berries := spec.get("berries", 0):
            lines.append(RewardLine(reward=reward, kind=RewardKind.BERRIES, amount=berries))
        for position, line in enumerate(lines, start=1):
            line.position = position
        RewardLine.objects.bulk_create(lines)
        # exclusions are a many-to-many, so they can only be set once the lines exist
        pool_specs = [pools] if isinstance(pools, dict) else (pools or [])
        pool_lines = [line for line in lines if line.is_pool]
        for line, pool_spec in zip(pool_lines, pool_specs, strict=False):
            excluded = [ball for ball in (self._ball(x) for x in pool_spec.get("exclude", [])) if ball]
            if excluded:
                line.exclude_balls.set(excluded)
        return reward
