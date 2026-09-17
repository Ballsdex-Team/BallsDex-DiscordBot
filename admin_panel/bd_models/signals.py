"""
Signals sent when treasures change hands.

`ownership_changed` is sent once the database transaction is committed, whenever treasures are created for a player,
given to someone else or deleted. Its arguments are:

- `gained`: `dict[int, list[BallInstance]]`, player primary key to the treasures they received or obtained
- `lost`: `dict[int, list[int]]`, player primary key to the IDs of the treasures they don't own anymore
- `created`: `set[int]`, IDs of the treasures in `gained` that were just created (as opposed to given)

Saving a `BallInstance` sends it automatically. Code moving treasures with `QuerySet.update` or `bulk_update` bypasses
model signals and must call `notify_ownership_change` itself.
"""

from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import Signal, receiver

from .models import BallInstance

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

ownership_changed = Signal()

_STATE_ATTRIBUTE = "_ownership_previous_state"


def notify_ownership_change(
    *,
    gained: "Mapping[int, Iterable[BallInstance]] | None" = None,
    lost: "Mapping[int, Iterable[int]] | None" = None,
    created: "Iterable[int]" = (),
):
    """
    Send `ownership_changed` once the current transaction is committed (immediately outside of a transaction).
    """
    gained_lists = {player_id: list(instances) for player_id, instances in (gained or {}).items()}
    lost_lists = {player_id: list(ids) for player_id, ids in (lost or {}).items()}
    gained_lists = {player_id: instances for player_id, instances in gained_lists.items() if instances}
    lost_lists = {player_id: ids for player_id, ids in lost_lists.items() if ids}
    if not gained_lists and not lost_lists:
        return
    created_ids = set(created)
    transaction.on_commit(
        lambda: ownership_changed.send_robust(
            sender=BallInstance, gained=gained_lists, lost=lost_lists, created=created_ids
        )
    )


@receiver(pre_save, sender=BallInstance)
def remember_previous_owner(
    sender: type[BallInstance], instance: BallInstance, raw: bool = False, update_fields: Any = None, **kwargs
):
    if raw or instance._state.adding or instance.pk is None:
        return
    if update_fields is not None and not {"player", "player_id", "deleted"}.intersection(update_fields):
        return
    previous = BallInstance.all_objects.filter(pk=instance.pk).values("player_id", "deleted").first()
    setattr(instance, _STATE_ATTRIBUTE, previous)


@receiver(post_save, sender=BallInstance)
def detect_ownership_change(
    sender: type[BallInstance], instance: BallInstance, created: bool, raw: bool = False, **kwargs
):
    previous = instance.__dict__.pop(_STATE_ATTRIBUTE, None)
    if raw:
        return
    if created:
        if not instance.deleted:
            notify_ownership_change(gained={instance.player_id: [instance]}, created=[instance.pk])
        return
    if previous is None:
        return

    gained: dict[int, list[BallInstance]] = {}
    lost: dict[int, list[int]] = {}
    if previous["player_id"] != instance.player_id:
        if not previous["deleted"]:
            lost[previous["player_id"]] = [instance.pk]
        if not instance.deleted:
            gained[instance.player_id] = [instance]
    elif not previous["deleted"] and instance.deleted:
        lost[instance.player_id] = [instance.pk]
    notify_ownership_change(gained=gained, lost=lost)
