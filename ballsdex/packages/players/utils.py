from io import BytesIO
from typing import Any

import psycopg
from django.db import connection
from django.db.models import F, Func, OuterRef, Q, Subquery, TextField, Value
from django.db.models.functions import Upper

from bd_models.models import BallInstance, Player, Trade, TradeObject
from settings.models import settings


async def copy_to(body: str, *params: str) -> BytesIO:
    # To get a fast export, we want to use "COPY TO" and send the output, without processing it.
    # However, we have two problems
    # - Django ORM doesn't expose COPY methods, so we need to get the low-end psycopg cursor
    # - The query must be made async, but Django still uses the synchronous API of psycopg
    # For that reason, we will just instanciate our own async psycopg connection
    #
    # Sources:
    # https://www.psycopg.org/psycopg3/docs/advanced/async.html#async
    # https://www.psycopg.org/psycopg3/docs/basic/copy.html

    # get the connection parameters from django
    db_params: dict[str, Any] = connection.get_connection_params()
    # remove django's custom objects
    db_params.pop("cursor_factory", None)
    db_params.pop("context", None)

    async with await psycopg.AsyncConnection.connect(**db_params) as conn:
        async with conn.cursor() as cursor:
            async with cursor.copy(f"COPY ({body}) TO STDOUT WITH (FORMAT csv, HEADER)", params) as copy:  # pyright: ignore[reportArgumentType]
                buffer = BytesIO()
                # it's important to iterate the query to avoid unfinished commands
                async for row in copy:
                    buffer.write(row)
                buffer.seek(0)
    return buffer


async def get_items_csv(player: Player) -> BytesIO:
    """
    Get a CSV file with all items of the player.
    """
    queryset = (
        BallInstance.objects.with_stats()
        .filter(player=player)
        .annotate(
            hex_id=Upper(Func(F("id"), function="to_hex")),
            traded_with=F("trade_player__discord_id"),
            special_card=F("special__name"),
            **{settings.collectible_name: F("ball__country")},
        )
        .only("id", "catch_date", "attack_bonus", "health_bonus")
    )
    query, params = queryset.query.sql_with_params()
    return await copy_to(query, *(str(x) for x in params))


async def get_trades_csv(player: Player) -> BytesIO:
    """
    Get a CSV file with all trades of the player.
    """
    queryset = (
        Trade.objects.filter(Q(player1=player) | Q(player2=player))
        .order_by("date")
        .annotate(
            p1=F("player1__discord_id"),
            p1_sent=Subquery(
                TradeObject.objects.filter(trade_id=OuterRef("pk"), player_id=OuterRef("player1_id"))
                .annotate(
                    agg=Func(
                        Upper(Func(F("id"), function="to_hex")),
                        Value(";"),
                        function="string_agg",
                        output_field=TextField(),
                    )
                )
                .values("agg")
            ),
            p2=F("player2__discord_id"),
            p2_sent=Subquery(
                TradeObject.objects.filter(trade_id=OuterRef("pk"), player_id=OuterRef("player2_id"))
                .annotate(
                    agg=Func(
                        Upper(Func(F("id"), function="to_hex")),
                        Value(";"),
                        function="string_agg",
                        output_field=TextField(),
                    )
                )
                .values("agg")
            ),
        )
        .only("id", "date")
    )
    query, params = queryset.query.sql_with_params()
    return await copy_to(query, *(str(x) for x in params))
