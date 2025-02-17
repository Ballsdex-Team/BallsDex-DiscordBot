from typing import TYPE_CHECKING, Iterable

import discord
from discord.utils import format_dt

from ballsdex.core.models import BlacklistHistory, Player
from ballsdex.core.utils import menus
from ballsdex.core.utils.paginator import Pages
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class BlacklistViewFormat(menus.ListPageSource):
    def __init__(self, entries: Iterable[BlacklistHistory], user_id: int, bot: "BallsDexBot"):
        self.header = user_id
        self.bot = bot
        super().__init__(entries, per_page=1)

    async def format_page(self, menu: Pages, blacklist: BlacklistHistory) -> discord.Embed:
        embed = discord.Embed(
            title=f"Blacklist History for {self.header}",
            description=f"Type: {blacklist.action_type}\nReason: {blacklist.reason}",
            timestamp=blacklist.date,
        )
        if blacklist.moderator_id:
            moderator = await self.bot.fetch_user(blacklist.moderator_id)
            embed.add_field(
                name=(
                    "Blacklisted by"
                    if blacklist.action_type == "blacklist"
                    else "Unblacklisted by"
                ),
                value=f"{moderator.display_name} ({moderator.id})",
                inline=True,
            )
        embed.add_field(name="Action Time", value=format_dt(blacklist.date, "R"), inline=True)
        if settings.admin_url and (player := await Player.get_or_none(discord_id=self.header)):
            embed.add_field(
                name="\u200B",
                value="[View history online]"
                f"(<{settings.admin_url}/bd_models/player/{player.pk}/change/>)",
                inline=False,
            )
        embed.set_footer(
            text=(
                f"Blacklist History {menu.current_page + 1}/{menu.source.get_max_pages()}"
                " | Blacklist date: "
            )
        )
        return embed
