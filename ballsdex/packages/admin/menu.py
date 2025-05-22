from typing import TYPE_CHECKING

import discord
from discord.utils import format_dt

from ballsdex.core.utils import menus
from ballsdex.settings import settings
from bd_models.models import BlacklistHistory, Player

if TYPE_CHECKING:
    from django.db.models import QuerySet


class BlacklistViewFormat(menus.ModelPageSource[BlacklistHistory]):
    @classmethod
    async def new_blacklistview(cls, queryset: "QuerySet[BlacklistHistory]", user_id: int):
        cls.header = user_id
        return await super().new(queryset, per_page=1)

    async def format_page(self, menu, page) -> discord.Embed:
        blacklist = page[0]
        embed = discord.Embed(
            title=f"Blacklist History for {self.header}",
            description=f"Type: {blacklist.action_type}\nReason: {blacklist.reason}",
            timestamp=blacklist.date,
        )
        if blacklist.moderator_id:
            moderator = await menu.bot.fetch_user(blacklist.moderator_id)
            embed.add_field(
                name=("Blacklisted by" if blacklist.action_type == "blacklist" else "Unblacklisted by"),
                value=f"{moderator.display_name} ({moderator.id})",
                inline=True,
            )
        embed.add_field(name="Action Time", value=format_dt(blacklist.date, "R"), inline=True)
        if settings.admin_url and (player := await Player.objects.aget_or_none(discord_id=self.header)):
            embed.add_field(
                name="\u200b",
                value=f"[View history online](<{settings.admin_url}/bd_models/player/{player.pk}/change/>)",
                inline=False,
            )
        embed.set_footer(
            text=(f"Blacklist History {menu.current_page + 1}/{menu.source.get_max_pages()} | Blacklist date: ")
        )
        return embed
