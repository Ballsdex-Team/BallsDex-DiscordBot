from collections import defaultdict
from typing import TYPE_CHECKING, cast

import discord
from discord.ext import commands
from discord.ui import Button

from ballsdex.core.utils.paginator import FieldPageSource, Pages, TextPageSource
from ballsdex.settings import settings
from bd_models.models import Ball, GuildConfig

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

    @commands.hybrid_group(
        default_permissions=discord.Permissions(administrator=True), guild_ids=settings.admin_guild_ids
    )
    async def admin(self, ctx: commands.Context):
        """
        Bot admin commands.
        """
        await ctx.send_help(ctx.command)

    @admin.command()
    @commands.has_any_role(*settings.root_role_ids)
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
    @commands.has_any_role(*settings.root_role_ids)
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

        source = TextPageSource(text, prefix="```md\n", suffix="```")
        assert ctx.interaction  # TODO: handle normal cmds
        pages = Pages(ctx, source, compact=True)
        pages.remove_item(pages.stop_pages)
        await pages.start(ephemeral=True)

    @admin.command()
    @commands.has_any_role(*settings.root_role_ids)
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
    @commands.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
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

        entries: list[tuple[str, str]] = []
        for guild in guilds:
            if config := await GuildConfig.objects.aget_or_none(guild_id=guild.id):
                spawn_enabled = config.enabled and config.guild_id
            else:
                spawn_enabled = False

            field_name = f"`{guild.id}`"
            field_value = ""

            # highlight suspicious server names
            if any(x in guild.name.lower() for x in ("farm", "grind", "spam")):
                field_value += f"- :warning: **{guild.name}**\n"
            else:
                field_value += f"- {guild.name}\n"

            # highlight low member count
            if guild.member_count <= 3:  # type: ignore
                field_value += f"- :warning: **{guild.member_count} members**\n"
            else:
                field_value += f"- {guild.member_count} members\n"

            # highlight if spawning is enabled
            if spawn_enabled:
                field_value += "- :warning: **Spawn is enabled**"
            else:
                field_value += "- Spawn is disabled"

            entries.append((field_name, field_value))

        source = FieldPageSource(entries, per_page=25, inline=True)
        source.embed.set_author(name=f"{user} ({user.id})", icon_url=user.display_avatar.url)

        if len(guilds) > 1:
            source.embed.title = f"{len(guilds)} servers shared"
        else:
            source.embed.title = "1 server shared"

        if not self.bot.intents.members:
            source.embed.set_footer(
                text="\N{WARNING SIGN} The bot cannot be aware of the member's "
                "presence in servers, it is only aware of server ownerships."
            )

        pages = Pages(ctx, source, compact=True)
        pages.add_item(
            Button(
                style=discord.ButtonStyle.link,
                label="View profile",
                url=f"discord://-/users/{user.id}",
                emoji="\N{LEFT-POINTING MAGNIFYING GLASS}",
            )
        )
        await pages.start(ephemeral=True)
