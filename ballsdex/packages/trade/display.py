from typing import TYPE_CHECKING, Iterable

import discord

from ballsdex.core.models import Trade as TradeModel
from ballsdex.core.utils import menus
from ballsdex.core.utils.paginator import Pages
from ballsdex.packages.trade.trade_user import TradingUser

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class TradeViewFormat(menus.ListPageSource):
    def __init__(
        self,
        entries: Iterable[TradeModel],
        header: str,
        bot: "BallsDexBot",
        is_admin: bool = False,
        url: str | None = None,
    ):
        self.header = header
        self.url = url
        self.bot = bot
        self.is_admin = is_admin
        super().__init__(entries, per_page=1)

    async def format_page(self, menu: Pages, trade: TradeModel) -> discord.Embed:
        embed = discord.Embed(
            title=f"Trade history for {self.header}",
            description=f"Trade ID: `#{trade.pk:0X}`",
            url=self.url if self.is_admin else None,
            timestamp=trade.date,
        )
        embed.set_footer(
            text=f"Trade {menu.current_page + 1}/{menu.source.get_max_pages()} | Trade date: "
        )
        fill_trade_embed_fields(
            embed,
            self.bot,
            await TradingUser.from_trade_model(trade, trade.player1, self.bot, self.is_admin),
            await TradingUser.from_trade_model(trade, trade.player2, self.bot, self.is_admin),
            is_admin=self.is_admin,
        )
        return embed


def _get_prefix_emote(trader: TradingUser) -> str:
    if trader.cancelled:
        return "\N{NO ENTRY SIGN}"
    elif trader.accepted:
        return "\N{WHITE HEAVY CHECK MARK}"
    elif trader.locked:
        return "\N{LOCK}"
    else:
        return ""


def _get_trader_name(trader: TradingUser, is_admin: bool = False) -> str:
    if is_admin:
        blacklisted = "\N{NO MOBILE PHONES} " if trader.blacklisted else ""
        return f"{blacklisted}{_get_prefix_emote(trader)} {trader.user.name} ({trader.user.id})"
    else:
        return f"{_get_prefix_emote(trader)} {trader.user.name}"


def _build_list_of_strings(
    trader: TradingUser, bot: "BallsDexBot", short: bool = False
) -> list[str]:
    # this builds a list of strings always lower than 1024 characters
    # while not cutting in the middle of a line
    proposal: list[str] = [""]
    i = 0

    for countryball in trader.proposal:
        cb_text = countryball.description(short=short, include_emoji=True, bot=bot, is_trade=True)
        if trader.locked:
            text = f"- *{cb_text}*\n"
        else:
            text = f"- {cb_text}\n"
        if trader.cancelled:
            text = f"~~{text}~~"

        if len(text) + len(proposal[i]) > 950:
            # move to a new list element
            i += 1
            proposal.append("")
        proposal[i] += text

    if not proposal[0]:
        proposal[0] = "*Empty*"

    return proposal


def fill_trade_embed_fields(
    embed: discord.Embed,
    bot: "BallsDexBot",
    trader1: TradingUser,
    trader2: TradingUser,
    compact: bool = False,
    is_admin: bool = False,
):
    """
    Fill the fields of an embed with the items part of a trade.

    This handles embed limits and will shorten the content if needed.

    Parameters
    ----------
    embed: discord.Embed
        The embed being updated. Its fields are cleared.
    bot: BallsDexBot
        The bot object, used for getting emojis.
    trader1: TradingUser
        The player that initiated the trade, displayed on the left side.
    trader2: TradingUser
        The player that was invited to trade, displayed on the right side.
    compact: bool
        If `True`, display countryballs in a compact way. This should not be used directly.
    """
    embed.clear_fields()

    # first, build embed strings
    # to play around the limit of 1024 characters per field, we'll be using multiple fields
    # these vars are list of fields, being a list of lines to include
    trader1_proposal = _build_list_of_strings(trader1, bot, compact)
    trader2_proposal = _build_list_of_strings(trader2, bot, compact)

    # then display the text. first page is easy
    embed.add_field(
        name=_get_trader_name(trader1, is_admin),
        value=trader1_proposal[0],
        inline=True,
    )
    embed.add_field(
        name=_get_trader_name(trader2, is_admin),
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
            i += 1

        # always add an empty field at the end, otherwise the alignment is off
        embed.add_field(name="\u200B", value="\u200B", inline=True)

    if len(embed) > 6000:
        if not compact:
            return fill_trade_embed_fields(
                embed, bot, trader1, trader2, compact=True, is_admin=is_admin
            )
        else:
            embed.clear_fields()
            embed.add_field(
                name=_get_trader_name(trader1, is_admin),
                value=(
                    f"Trade too long, only showing last page:\n{trader1_proposal[-1]}"
                    f"\nTotal: {len(trader1.proposal)}"
                ),
                inline=True,
            )
            embed.add_field(
                name=_get_trader_name(trader2, is_admin),
                value=(
                    f"Trade too long, only showing last page:\n{trader2_proposal[-1]}\n"
                    f"Total: {len(trader2.proposal)}"
                ),
                inline=True,
            )
