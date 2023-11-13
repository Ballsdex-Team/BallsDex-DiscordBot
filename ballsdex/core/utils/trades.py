from typing import Iterable, List

import discord

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.models import Trade, TradeObject
from ballsdex.core.utils import menus


class TradeViewFormat(menus.ListPageSource):
    def __init__(self, entries: Iterable[Trade], header, bot):
        self.header = header
        self.bot = bot
        super().__init__(entries, per_page=1)

    async def format_page(self, menu, trade: Trade) -> discord.Embed:
        embed = discord.Embed(
            title=f"Trade History for {self.header}",
            description=f"Trade ID: {trade.id}",
            timestamp=trade.date,
        )
        player1balls = await trade.tradeobjects.filter(player=trade.player2).prefetch_related(
            "ballinstance"
        )
        player2balls = await trade.tradeobjects.filter(player=trade.player1).prefetch_related(
            "ballinstance"
        )
        embed.set_footer(
            text=f"Trade {menu.current_page + 1 }/{menu.source.get_max_pages()} | Trade date: "
        )
        embed = await get_embed(embed, trade, player1balls, player2balls, self.bot)
        return embed


async def get_embed(
    embed: discord.Embed,
    trade: Trade,
    player1balls: List[TradeObject],
    player2balls: List[TradeObject],
    bot: "BallsDexBot",
    compact: bool = False,
) -> discord.Embed:
    """
    Update the fields in the embed according to their current proposals.

    Parameters
    ----------
    compact: bool
        If `True`, display countryballs in a compact way.
    """
    embed.clear_fields()

    # first, build embed strings
    # to play around the limit of 1024 characters per field, we'll be using multiple fields
    # these vars are list of fields, being a list of lines to include
    trader1_proposal = _build_list_of_strings(player1balls, bot, compact)
    trader2_proposal = _build_list_of_strings(player2balls, bot, compact)
    user1name = await bot.fetch_user(trade.player1.discord_id)
    user2name = await bot.fetch_user(trade.player2.discord_id)

    # then display the text. first page is easy
    embed.add_field(
        name=f"{user1name if user1name else trade.player1.discord_id} received",
        value=trader1_proposal[0],
        inline=True,
    )
    embed.add_field(
        name=f"{user2name if user2name else trade.player2.discord_id} received",
        value=trader2_proposal[0],
        inline=True,
    )

    if len(trader1_proposal) > 1 or len(trader2_proposal) > 1:
        # we'll have to trick for displaying the other pages
        # fields have to stack themselves vertically
        # to do this, we add a 3rd empty field on each line (since 3 fields per line)
        i = 1
        while i < len(trader1_proposal) or i < len(trader2_proposal):
            embed.add_field(name="\u200B", value="\u200B", inline=True)  # empty

            if i < len(trader1_proposal):
                embed.add_field(name="\u200B", value=trader1_proposal[i], inline=True)
            else:
                embed.add_field(name="\u200B", value="\u200B", inline=True)

            if i < len(trader2_proposal):
                embed.add_field(name="\u200B", value=trader2_proposal[i], inline=True)
            else:
                embed.add_field(name="\u200B", value="\u200B", inline=True)
            # always add an empty field at the end, otherwise the alignment is off
            embed.add_field(name="\u200B", value="\u200B", inline=True)
            i += 1

    if len(embed) > 6000 and not compact:
        await get_embed(embed, trade, player1balls, player2balls, bot, compact=True)
    return embed


def _build_list_of_strings(
    balls: List[TradeObject],
    bot: "BallsDexBot",
    short: bool = False,
) -> list[str]:
    # this builds a list of strings always lower than 1024 characters
    # while not cutting in the middle of a line
    proposal: list[str] = [""]
    i = 0

    for trade in balls:
        cb_text = trade.ballinstance.description(short=short, include_emoji=True, bot=bot)
        text = f"- {cb_text}\n"

        if len(text) + len(proposal[i]) > 1024:
            # move to a new list element
            i += 1
            proposal.append("")
        proposal[i] += text

    if not proposal[0]:
        proposal[0] = "*Empty*"

    return proposal
