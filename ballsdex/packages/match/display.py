from typing import TYPE_CHECKING, Iterable

import discord

from ballsdex.core.models import Trade as TradeModel
from ballsdex.core.utils import menus
from ballsdex.core.utils.paginator import Pages
from ballsdex.packages.match.match_user import MatchingUser

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class MatchViewFormat(menus.ListPageSource):
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

    async def format_page(self, menu: Pages, match: TradeModel) -> discord.Embed:
        embed = discord.Embed(
            title=f"Match history for {self.header}",
            description=f"Match ID: {match.pk:0X}",
            url=self.url if self.is_admin else None,
            timestamp=match.date,
        )
        embed.set_footer(
            text=f"Match {menu.current_page + 1}/{menu.source.get_max_pages()} | Match date: "
        )
        fill_match_embed_fields(
            embed,
            self.bot,
            await MatchingUser.from_match_model(match, match.player1, self.bot, self.is_admin),
            await MatchingUser.from_match_model(match, match.player2, self.bot, self.is_admin),
            is_admin=self.is_admin,
        )
        return embed


def _get_prefix_emote(player: MatchingUser) -> str:
    if player.cancelled:
        return "\N{NO ENTRY SIGN}"
    elif player.matched:
        return "\N{TROPHY}"
    elif player.locked:
        return "\N{LOCK}"
    else:
        return ""


def _get_player_name(player: MatchingUser, is_admin: bool = False) -> str:
    if is_admin:
        blacklisted = "\N{NO MOBILE PHONES} " if player.blacklisted else ""
        return f"{blacklisted}{_get_prefix_emote(player)} {player.user.name} ({player.user.id})"
    else:
        return f"{_get_prefix_emote(player)} {player.user.name}"


def _build_list_of_strings(
    player: MatchingUser, bot: "BallsDexBot", short: bool = False
) -> list[str]:
    # this builds a list of strings always lower than 1024 characters
    # while not cutting in the middle of a line
    bet: list[str] = [""]
    i = 0

    for countryball in player.bet:
        cb_text = countryball.description(short=short, include_emoji=True, bot=bot, is_trade=True)
        if player.locked:
            text = f"- *{cb_text}*\n"
        else:
            text = f"- {cb_text}\n"
        if player.cancelled:
            text = f"~~{text}~~"

        if len(text) + len(bet[i]) > 950:
            # move to a new list element
            i += 1
            bet.append("")
        bet[i] += text

    if not bet[0]:
        bet[0] = "*Empty*"

    return bet


def fill_match_embed_fields(
    embed: discord.Embed,
    bot: "BallsDexBot",
    player1: MatchingUser,
    player2: MatchingUser,
    compact: bool = False,
    is_admin: bool = False,
):
    """
    Fill the fields of an embed with the items part of a match.

    This handles embed limits and will shorten the content if needed.

    Parameters
    ----------
    embed: discord.Embed
        The embed being updated. Its fields are cleared.
    bot: BallsDexBot
        The bot object, used for getting emojis.
    player1: MatchingUser
        The player that initiated the match, displayed on the left side.
    player2: MatchingUser
        The player that was invited to match, displayed on the right side.
    compact: bool
        If `True`, display countryballs in a compact way. This should not be used directly.
    """
    embed.clear_fields()

    # first, build embed strings
    # to play around the limit of 1024 characters per field, we'll be using multiple fields
    # these vars are list of fields, being a list of lines to include
    player1_bet = _build_list_of_strings(player1, bot, compact)
    player2_bet = _build_list_of_strings(player2, bot, compact)

    # then display the text. first page is easy
    embed.add_field(
        name=_get_player_name(player1, is_admin),
        value=player1_bet[0],
        inline=True,
    )
    embed.add_field(
        name=_get_player_name(player2, is_admin),
        value=player2_bet[0],
        inline=True,
    )

    if len(player1_bet) > 1 or len(player2_bet) > 1:
        # we'll have to trick for displaying the other pages
        # fields have to stack themselves vertically
        # to do this, we add a 3rd empty field on each line (since 3 fields per line)
        i = 1
        while i < len(player1_bet) or i < len(player2_bet):
            embed.add_field(name="\u200B", value="\u200B", inline=True)  # empty

            if i < len(player1_bet):
                embed.add_field(name="\u200B", value=player1_bet[i], inline=True)
            else:
                embed.add_field(name="\u200B", value="\u200B", inline=True)

            if i < len(player2_bet):
                embed.add_field(name="\u200B", value=player2_bet[i], inline=True)
            else:
                embed.add_field(name="\u200B", value="\u200B", inline=True)
            i += 1

        # always add an empty field at the end, otherwise the alignment is off
        embed.add_field(name="\u200B", value="\u200B", inline=True)

    if len(embed) > 6000:
        if not compact:
            return fill_match_embed_fields(
                embed, bot, player1, player2, compact=True, is_admin=is_admin
            )
        else:
            embed.clear_fields()
            embed.add_field(
                name=_get_player_name(player1, is_admin),
                value=(
                    f"Bet too long, only showing last page:\n{player1_bet[-1]}"
                    f"\nTotal: {len(player1.bet)}"
                ),
                inline=True,
            )
            embed.add_field(
                name=_get_player_name(player2, is_admin),
                value=(
                    f"Bet too long, only showing last page:\n{player2_bet[-1]}\n"
                    f"Total: {len(player2.bet)}"
                ),
                inline=True,
            )
