import discord
from discord.ui import ActionRow, Button, Container, Section, Separator, TextDisplay, Thumbnail
from discord.utils import format_dt
from django.db.models import QuerySet
from django.urls import reverse

from ballsdex.core.utils import menus
from bd_models.models import BlacklistHistory, Player
from settings.models import settings


class BlacklistHistoryFormatter(menus.Formatter[QuerySet[BlacklistHistory], Container]):
    def __init__(self, item: Container, user: discord.User):
        super().__init__(item)
        self.user = user

    async def format_page(self, page):
        blacklist = await page.aget()
        container = self.item
        container.clear_items()
        section = Section(
            TextDisplay(f"# Blacklist history for {self.user.mention}"),
            TextDisplay(f"Type: {blacklist.action_type}"),
            TextDisplay(f"Action Time: {format_dt(blacklist.date, 'R')}"),
            accessory=Thumbnail(self.user.display_avatar.url),
        )
        container.add_item(section)
        if blacklist.moderator_id:
            moderator = await self.menu.bot.fetch_user(blacklist.moderator_id)
            container.add_item(Separator())
            action_type = "Blacklisted" if blacklist.action_type == "blacklist" else "Unblacklisted"
            container.add_item(
                Section(
                    TextDisplay(f"### {action_type} by {moderator.mention}"),
                    TextDisplay(f"### Reason\n{blacklist.reason}"),
                    accessory=Thumbnail(moderator.display_avatar.url),
                )
            )
        if player := await Player.objects.aget_or_none(discord_id=self.user.id):
            container.add_item(
                ActionRow(
                    Button(
                        url=f"{settings.site_base_url}{reverse('admin:bd_models_player_change', args=(player.pk,))}",
                        label="View history online",
                    )
                )
            )
        container.add_item(
            TextDisplay(f"-# Blacklist history {self.menu.current_page + 1}/{self.menu.source.get_max_pages()}")
        )
