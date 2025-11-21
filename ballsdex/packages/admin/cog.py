import logging
from collections import defaultdict
from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import ActionRow, Button, Container, Section, TextDisplay

from ballsdex.core.discord import LayoutView
from ballsdex.core.utils import checks
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.menus import (
    ItemFormatter,
    ListSource,
    Menu,
    TextFormatter,
    TextSource,
    dynamic_chunks,
    iter_to_async,
)
from bd_models.models import Ball, GuildConfig
from settings.models import settings

from .balls import balls as balls_group
from .blacklist import blacklist as blacklist_group
from .blacklist import blacklistguild as blacklist_guild_group
from .flags import RarityFlags, StatusFlags
from .history import history as history_group
from .info import info as info_group
from .logs import logs as logs_group
from .money import money as money_group

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
    from ballsdex.packages.countryballs.cog import CountryBallsSpawner
    from ballsdex.packages.trade.cog import Trade

log = logging.getLogger("ballsdex.packages.admin")


class SyncView(LayoutView):
    def __init__(self, cog: "Admin", *, timeout: float | None = 180) -> None:
        super().__init__(timeout=timeout)
        self.cog = cog

    text = TextDisplay("Admin commands are already synced here. What would you like to do?")
    action_row = ActionRow()

    @action_row.button(
        label="Synchronize",
        style=discord.ButtonStyle.primary,
        emoji="\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS}",
    )
    async def sync(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        assert interaction.guild
        self.stop()
        await interaction.response.defer()
        if not interaction.client.tree.get_command("admin", guild=interaction.guild):
            interaction.client.tree.add_command(self.cog.admin.app_command, guild=interaction.guild)
        await interaction.client.tree.sync(guild=interaction.guild)
        self.sync.disabled = True
        self.remove.disabled = True
        self.text.content += (
            "\n\nCommands have been refreshed. You may need to reload your Discord client to see the changes applied."
        )
        await interaction.edit_original_response(view=self)

    @action_row.button(
        label="Remove", style=discord.ButtonStyle.danger, emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}"
    )
    async def remove(self, interaction: discord.Interaction["BallsDexBot"], button: Button):
        assert interaction.guild
        self.stop()
        await interaction.response.defer()
        interaction.client.tree.remove_command("admin", guild=interaction.guild)
        await interaction.client.tree.sync(guild=interaction.guild)
        self.sync.disabled = True
        self.remove.disabled = True
        self.text.content += (
            "\n\nCommands have been removed. You may need to reload your Discord client to see the changes applied."
        )
        await interaction.edit_original_response(view=self)
        log.info(f"Admin commands removed from guild {interaction.guild.id} by {interaction.user}")


class Admin(commands.Cog):
    """
    Bot admin commands.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

        self.admin.add_command(info_group)
        self.admin.add_command(balls_group)
        self.admin.add_command(blacklist_group)
        self.admin.add_command(blacklist_guild_group)
        self.admin.add_command(history_group)
        self.admin.add_command(logs_group)
        self.admin.add_command(money_group)

    async def cog_app_command_error(
        self, interaction: discord.Interaction["BallsDexBot"], error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CommandSignatureMismatch):
            assert self.bot.user
            await interaction.response.send_message(
                "Admin commands are desynchronized and needs to be re-synced. "
                f"Run `{self.bot.user.mention} admin syncslash` to fix this.",
                ephemeral=True,
            )
            interaction.extras["handled"] = True

    @commands.hybrid_group()
    @app_commands.guilds()
    @app_commands.default_permissions(administrator=True)
    @commands.has_permissions(administrator=True)
    @checks.is_staff()
    async def admin(self, ctx: commands.Context):
        """
        Bot admin commands.
        """
        await ctx.send_help(ctx.command)

    @admin.command(with_app_command=False)
    @commands.is_owner()
    @commands.guild_only()
    async def syncslash(self, ctx: commands.Context["BallsDexBot"]):
        """
        Synchronize all the admin commands in the current server, or remove them if already existing.
        """
        assert ctx.guild
        commands = await self.bot.tree.fetch_commands(guild=ctx.guild)
        if commands:
            view = SyncView(self)
            await ctx.send(view=view)
        else:
            view = ConfirmChoiceView(ctx, accept_message="Registering commands...")
            await ctx.send(
                "Would you like to add admin slash commands in this server? "
                "They can only be used with the appropriate Django permissions",
                view=view,
            )
            await view.wait()
            if not view.value:
                return
            async with ctx.typing():
                self.bot.tree.add_command(self.admin.app_command, guild=ctx.guild)
                await self.bot.tree.sync(guild=ctx.guild)
                log.info(f"Admin commands added to guild {ctx.guild.id} by {ctx.author}")
                await ctx.send(
                    "Admin slash commands added.\nYou need admin permissions in this server to view them "
                    f"(this can be changed [here](discord://-/guilds/{ctx.guild.id}/settings/integrations)). You might "
                    "need to refresh your Discord client to view them."
                )

    @admin.command()
    @checks.is_superuser()
    async def status(self, ctx: commands.Context["BallsDexBot"], *, flags: StatusFlags):
        """
        Change the status of the bot. Provide at least status or text.
        """
        if not flags.status and not flags.name and not flags.state:
            await ctx.send("You must provide at least `status`, `name` or `state`.", ephemeral=True)
            return

        activity: discord.Activity | None = None
        if flags.activity_type == discord.ActivityType.custom and flags.name and not flags.state:
            await ctx.send("You must provide `state` for custom activities. `name` is unused.", ephemeral=True)
            return
        if flags.activity_type != discord.ActivityType.custom and not flags.name:
            await ctx.send("You must provide `name` for pre-defined activities.", ephemeral=True)
            return
        if flags.name or flags.state:
            activity = discord.Activity(name=flags.name or flags.state, state=flags.state, type=flags.activity_type)
        await self.bot.change_presence(status=flags.status, activity=activity)
        await ctx.send("Status updated.", ephemeral=True)

    @admin.command()
    @checks.is_superuser()
    async def trade_lockdown(self, ctx: commands.Context["BallsDexBot"], *, reason: str):
        """
        Cancel all ongoing trades and lock down further trades from being started.

        Parameters
        ----------
        reason: str
            The reason of the lockdown. This will be displayed to all trading users.
        """
        cog = cast("Trade | None", self.bot.get_cog("Trade"))
        if not cog:
            await ctx.send("The trade cog is not loaded.", ephemeral=True)
            return

        await ctx.defer()
        result = await cog.cancel_all_trades(reason)

        assert self.bot.user
        prefix = settings.prefix if self.bot.intents.message_content else f"{self.bot.user.mention} "

        if not result:
            await ctx.send(
                "All trades were successfully cancelled, and further trades cannot be started "
                f'anymore.\nTo enable trades again, the bot owner must use the "{prefix}reload '
                'trade" command.'
            )
        else:
            await ctx.send(
                "Lockdown mode enabled, trades can no longer be started. "
                f"While cancelling ongoing trades, {len(result)} failed to cancel, check your "
                "logs for info.\nTo enable trades again, the bot owner must use the "
                f'"{prefix}reload trade" command.'
            )

    @admin.command()
    @checks.has_permissions("bd_models.view_ball")
    async def rarity(self, ctx: commands.Context["BallsDexBot"], *, flags: RarityFlags):
        """
        Generate a list of countryballs ranked by rarity.
        """
        text = ""
        balls_queryset = Ball.objects.all().order_by("rarity")
        if not flags.include_disabled:
            balls_queryset = balls_queryset.filter(rarity__gt=0, enabled=True)
        sorted_balls = [x async for x in balls_queryset]

        if flags.chunked:
            indexes: dict[float, list[Ball]] = defaultdict(list)
            for ball in sorted_balls:
                indexes[ball.rarity].append(ball)
            i = 1
            for chunk in indexes.values():
                for ball in chunk:
                    text += f"{i}. {ball.country}\n"
                i += len(chunk)
        else:
            for i, ball in enumerate(sorted_balls, start=1):
                text += f"{i}. {ball.country}\n"

        view = discord.ui.LayoutView()
        text_display = discord.ui.TextDisplay("")
        view.add_item(text_display)
        menu = Menu(self.bot, view, TextSource(text, prefix="```md\n", suffix="```"), TextFormatter(text_display))
        await menu.init()
        await ctx.send(view=view)

    @admin.command()
    @checks.is_superuser()
    async def cooldown(self, ctx: commands.Context["BallsDexBot"], guild_id: str | None = None):
        """
        Show the details of the spawn cooldown system for the given server

        Parameters
        ----------
        guild_id: int | None
            ID of the server you want to inspect. If not given, inspect the current server.
        """
        if guild_id:
            try:
                guild = self.bot.get_guild(int(guild_id))
            except ValueError:
                await ctx.send("Invalid guild ID. Please make sure it's a number.", ephemeral=True)
                return
        else:
            guild = ctx.guild
        if not guild:
            await ctx.send("The given guild could not be found.", ephemeral=True)
            return

        spawn_manager = cast("CountryBallsSpawner", self.bot.get_cog("CountryBallsSpawner")).spawn_manager
        await spawn_manager.admin_explain(ctx, guild)

    @admin.command()
    async def guilds(self, ctx: commands.Context["BallsDexBot"], user: discord.User):
        """
        Shows the guilds shared with the specified user. Provide either user or user_id.

        Parameters
        ----------
        user: discord.User
            The user you want to check, if available in the current server.
        """
        if self.bot.intents.members:
            guilds = user.mutual_guilds
        else:
            guilds = [x for x in self.bot.guilds if x.owner_id == user.id]

        if not guilds:
            if self.bot.intents.members:
                await ctx.send(f"The user does not own any server with {settings.bot_name}.", ephemeral=True)
            else:
                await ctx.send(
                    f"The user does not own any server with {settings.bot_name}.\n"
                    ":warning: *The bot cannot be aware of the member's presence in servers, "
                    "it is only aware of server ownerships.*",
                    ephemeral=True,
                )
            return

        entries: list[TextDisplay] = []
        for guild in guilds:
            if config := await GuildConfig.objects.aget_or_none(guild_id=guild.id):
                spawn_enabled = config.enabled and config.guild_id
            else:
                spawn_enabled = False

            text = f"## {guild.name}\n"

            # highlight suspicious server names
            if any(x in guild.name.lower() for x in ("farm", "grind", "spam")):
                text += f"- :warning: **{guild.name}**\n"
            else:
                text += f"- {guild.name}\n"

            # highlight low member count
            if guild.member_count <= 3:  # type: ignore
                text += f"- :warning: **{guild.member_count} members**\n"
            else:
                text += f"- {guild.member_count} members\n"

            # highlight if spawning is enabled
            if spawn_enabled:
                text += "- :warning: **Spawn is enabled**"
            else:
                text += "- Spawn is disabled"

            entries.append(TextDisplay(text))

        view = LayoutView()
        container = Container()
        view.add_item(container)
        section = Section(
            TextDisplay(f"## {len(guilds)} servers shared"),
            TextDisplay(f"{user.mention} ({user.id})"),
            accessory=Button(
                style=discord.ButtonStyle.link,
                label="View profile",
                url=f"discord://-/users/{user.id}",
                emoji="\N{LEFT-POINTING MAGNIFYING GLASS}",
            ),
        )
        container.add_item(section)

        if not self.bot.intents.members:
            section.add_item(
                TextDisplay(
                    "\N{WARNING SIGN} The bot cannot be aware of the member's "
                    "presence in servers, it is only aware of server ownerships."
                )
            )

        pages = Menu(
            self.bot, view, ListSource(await dynamic_chunks(view, iter_to_async(entries))), ItemFormatter(container, 1)
        )
        await pages.init()
        await ctx.send(view=view, ephemeral=True)
