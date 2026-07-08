from typing import TYPE_CHECKING

import discord
from currency_app.models import CurrencySettings
from discord import app_commands
from discord.ext import commands

from ballsdex.core.utils.menus.old import FieldPageSource, Pages
from ballsdex.core.utils.utils import inventory_privacy, is_staff
from ballsdex.settings import settings
from bd_models.models import BallInstance, Player
from collectible_app.models import Collectible as CollectibleModel
from collectible_app.models import CollectibleInstance
from settings.models import settings
from settings.utils import format_currency

from .transformers import CollectibleTransform

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class Collectible(commands.GroupCog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    async def list(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Check all available collectibles.
        """
        await interaction.response.defer(thinking=True)
        entries: list[tuple[str, str]] = []
        collectibles = [x async for x in CollectibleModel.objects.order_by("name", "created_at").all()]

        for collectible in collectibles:
            emoji = self.bot.get_emoji(collectible.emoji_id) if collectible.emoji_id else ""
            price = "Free" if collectible.price is None else format_currency(collectible.price, False, self.bot)

            if collectible.description:
                desc = f"{collectible.description}\n\nPrice: {price}\n**__Requirements:__**\n"
            else:
                desc = f"Price: {price}**__Requirements:__**\n"

            if not collectible.has_requirements:
                desc += "You don't need any requirements to buy this collectible.\n"
            else:
                if collectible.cached_ball:
                    desc += f"**Required Treasure:** {collectible.cached_ball.country}\n"
                if collectible.cached_special:
                    desc += f"**Required Special:** {collectible.cached_special.name}\n"
                if collectible.amount:
                    desc += f"**Amount:** {collectible.amount}\n"

            entries.append((f"{emoji} {collectible.name}", desc))

        source = FieldPageSource(entries, per_page=5)
        source.embed.title = "Collectibles"
        source.embed.description = "Here is a list of available collectibles."

        pages = Pages(source, interaction=interaction, compact=True)
        await pages.start()

    @app_commands.command()
    async def claim(self, interaction: discord.Interaction["BallsDexBot"], collectible: CollectibleTransform):
        """
        Claim a collectible

        Parameters
        ----------
        collectible: Collectible
            The collectible to claim.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)

        if await CollectibleInstance.objects.filter(player=player, collectible=collectible).aexists():
            await interaction.followup.send("You already have this collectible.")
            return

        if collectible.has_requirements:
            if not await self.check_requirements(player, collectible):
                await interaction.followup.send("You don't complete with requirements.")
                return

        if collectible.price:
            if collectible.price > player.money:
                emoji = self.bot.get_emoji(collectible.emoji_id) if collectible.emoji_id else ""
                await interaction.followup.send(
                    f"You don't enough {settings.currency_display_plural(self.bot)} to buy "
                    f"**{emoji} {collectible.name}**\n"
                    f"Your actual balance: **{format_currency(collectible.price, False, self.bot)}**"
                )
                return
            else:
                await player.remove_money(collectible.price)

        await CollectibleInstance.objects.acreate(player=player, collectible=collectible)
        await interaction.followup.send(f"You've claimed **{collectible.name}!** Congratulations!")
        return

    @app_commands.command()
    async def completion(self, interaction: discord.Interaction["BallsDexBot"], user: discord.User | None = None):
        """
        Show your current collectible completion of the BallsDex.

        Parameters
        ----------
        user: discord.User
            The user whose collectible completion you want to view, if not yours.
        """
        user_obj = user or interaction.user
        await interaction.response.defer(thinking=True)
        if user is not None:
            try:
                player = await Player.objects.aget(discord_id=user_obj.id)
            except Player.DoesNotExist:
                await interaction.followup.send(f"{user_obj.name} doesn't have any collectibles yet.")
                return
            if user.id in self.bot.blacklist and not is_staff(interaction):
                await interaction.followup.send("You cannot view the completion of a blacklisted user.", ephemeral=True)
                return

            interaction_player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)

            blocked = await player.is_blocked(interaction_player)
            if blocked and not is_staff(interaction):
                await interaction.followup.send(
                    "You cannot view the collectible completion of a user that has blocked you.", ephemeral=True
                )
                return

            if await inventory_privacy(self.bot, interaction, player, user_obj) is False:
                return
        # Filter disabled balls, they do not count towards progression
        # Only ID and emoji is interesting for us
        bot_countryballs = {x.pk: x.emoji_id async for x in CollectibleModel.objects.all()}

        # Set of ball IDs owned by the player
        query = CollectibleInstance.objects.filter(player__discord_id=user_obj.id)

        if not bot_countryballs:
            await interaction.followup.send("There are no collectibles registered on this bot yet.", ephemeral=True)
            return

        owned_countryballs = set(
            [
                x[0]
                async for x in query.distinct().values_list("collectible_id")  # Do not query everything
            ]
        )

        entries: list[tuple[str, str]] = []

        def fill_fields(title: str, emoji_ids: set[int]):
            # check if we need to add "(continued)" to the field name
            first_field_added = False
            buffer = ""

            for emoji_id in emoji_ids:
                emoji = self.bot.get_emoji(emoji_id)
                if not emoji:
                    continue

                text = f"{emoji} "
                if len(buffer) + len(text) > 1024:
                    # hitting embed limits, adding an intermediate field
                    if first_field_added:
                        entries.append(("\u200b", buffer))
                    else:
                        entries.append((f"__**{title}**__", buffer))
                        first_field_added = True
                    buffer = ""
                buffer += text

            if buffer:  # add what's remaining
                if first_field_added:
                    entries.append(("\u200b", buffer))
                else:
                    entries.append((f"__**{title}**__", buffer))

        if owned_countryballs:
            # Getting the list of emoji IDs from the IDs of the owned countryballs
            fill_fields("Owned collectibles", set(bot_countryballs[x] for x in owned_countryballs))
        else:
            entries.append(("__**Owned collectibles**__", "Nothing yet."))

        if missing := set(y for x, y in bot_countryballs.items() if x not in owned_countryballs):
            fill_fields("Missing collectibles", missing)
        else:
            entries.append(
                ("__**:tada: No missing collectibles, congratulations! :tada:**__", "\u200b")
            )  # force empty field value

        source = FieldPageSource(entries, per_page=5, inline=False, clear_description=False)
        source.embed.description = (
            f"{settings.bot_name} collectibles progression: "
            f"**{round(len(owned_countryballs) / len(bot_countryballs) * 100, 1)}%**"
        )
        source.embed.colour = discord.Colour.blurple()
        source.embed.set_author(name=user_obj.display_name, icon_url=user_obj.display_avatar.url)

        pages = Pages(source=source, interaction=interaction, compact=True)
        await pages.start()

    async def check_requirements(self, player: Player, collectible: CollectibleModel) -> bool:
        query = BallInstance.objects.filter(player=player)
        if collectible.ball:
            query = query.filter(ball=collectible.ball)
        if collectible.special:
            query = query.filter(special=collectible.special)
        if collectible.amount:
            return await query.acount() >= collectible.amount

        return await query.aexists()
