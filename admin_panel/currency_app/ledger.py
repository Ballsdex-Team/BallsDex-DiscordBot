"""
Single entry point for every berry movement in the bot.

Any change to a player's balance should go through `adjust_money` (or the async
`aadjust_money`), which applies the change and writes the matching `BerryTransaction`
row in the same transaction. `Player.add_money` / `Player.remove_money` are wired to it
too, so code that never heard of this module still ends up in the ledger — with an
`UNKNOWN` reason, which is exactly what an audit should surface.

Every row stores `balance_after`, which makes the ledger self-auditing: replaying a
player's rows in order must reproduce their current balance. A jump between one row's
`balance_after` and the next row's means berries moved somewhere that bypassed this
module, and the admin list flags it.
"""

from asgiref.sync import sync_to_async
from django.db import transaction

from ballsdex.core.game_events import Event, EventContext, bus
from bd_models.models import Player


def adjust_money(
    player: "Player | int",
    amount: int,
    *,
    reason: str = "",
    description: str = "",
    server_id: int | None = None,
) -> int:
    """
    Applies a signed berry change to a player and records it in the ledger.

    `amount` is signed: positive credits the player, negative debits them. The player row
    is locked for the duration, so the recorded `balance_after` is always the real balance
    and concurrent adjustments can't interleave.

    Accepts either a `Player` instance or a player primary key. When given an instance, its
    in-memory `money` is updated to the new balance so callers can keep using it.

    Raises `ValueError` if the player can't afford a debit.
    """
    from .models import BerryTransaction

    player_id = player if isinstance(player, int) else player.pk

    with transaction.atomic():
        locked = Player.objects.select_for_update().get(pk=player_id)
        new_balance = locked.money + amount
        if new_balance < 0:
            raise ValueError("Not enough money")

        locked.money = new_balance
        locked.save(update_fields=("money",))

        BerryTransaction.objects.create(
            player_id=player_id,
            amount=amount,
            balance_after=new_balance,
            reason=reason or BerryTransaction.Reason.UNKNOWN,
            description=description[: BerryTransaction.DESCRIPTION_MAX_LENGTH],
            server_id=server_id,
        )

        # every berry movement is an event, which is what lets goals count what players spend and earn without
        # each shop having to announce its own sales. Sent once the movement is committed, never before.
        if amount:
            context = EventContext(
                amount=amount, reason=reason or BerryTransaction.Reason.UNKNOWN, server_id=server_id
            )
            transaction.on_commit(lambda: bus.dispatch_soon(player_id, Event.ECONOMY, context=context))

    if not isinstance(player, int):
        player.money = new_balance
    return new_balance


async def aadjust_money(
    player: "Player | int",
    amount: int,
    *,
    reason: str = "",
    description: str = "",
    server_id: int | None = None,
) -> int:
    """Async wrapper around [`adjust_money`][]."""
    return await sync_to_async(adjust_money)(
        player, amount, reason=reason, description=description, server_id=server_id
    )


def adjust_money_to(
    player: "Player | int",
    balance: int,
    *,
    reason: str = "",
    description: str = "",
    server_id: int | None = None,
) -> int:
    """
    Sets a player's balance to an absolute value, recording the difference as the movement.

    For the handful of places that overwrite a balance outright (admin `/money set`, wipes)
    rather than adding to it. The delta is computed under the same row lock, so the ledger
    stays continuous instead of showing an unexplained jump.
    """
    player_id = player if isinstance(player, int) else player.pk

    with transaction.atomic():
        current = Player.objects.select_for_update().values_list("money", flat=True).get(pk=player_id)
        return adjust_money(
            player, balance - current, reason=reason, description=description, server_id=server_id
        )


async def aadjust_money_to(
    player: "Player | int",
    balance: int,
    *,
    reason: str = "",
    description: str = "",
    server_id: int | None = None,
) -> int:
    """Async wrapper around [`adjust_money_to`][]."""
    return await sync_to_async(adjust_money_to)(
        player, balance, reason=reason, description=description, server_id=server_id
    )


def reset_all_balances(balance: int, author_id: int) -> int:
    """
    Sets every player's balance at once, leaving one ledger row per player behind.

    Used by the `/money setdefault --force` wipe. Without the ledger rows, that wipe would
    make the audit report every single player as inconsistent, which would bury any real
    problem. Returns how many players were affected.
    """
    from .models import BerryTransaction

    with transaction.atomic():
        players = list(Player.objects.select_for_update().values_list("pk", "money"))
        BerryTransaction.objects.bulk_create(
            [
                BerryTransaction(
                    player_id=player_id,
                    amount=balance - current,
                    balance_after=balance,
                    reason=BerryTransaction.Reason.ADMIN_ADJUST,
                    description=f"Global balance reset by {author_id}",
                )
                for player_id, current in players
                if current != balance
            ],
            batch_size=1000,
        )
        Player.objects.all().update(money=balance)
    return len(players)
