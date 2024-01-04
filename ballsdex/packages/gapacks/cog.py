import discord
import logging
import random
import re

from discord.utils import get
from discord import app_commands
from discord.ext import commands

from ballsdex.settings import settings
from ballsdex.core.utils.paginator import FieldPageSource, Pages
from ballsdex.settings import settings
from ballsdex.core.models import Player, BallInstance, specials, balls 
from ballsdex.packages.countryballs.countryball import CountryBall

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.gaPacks")

class gaPacks(commands.Cog):
    """
    Simple vote commands.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    @app_commands.checks.cooldown(1, 10, key=lambda i: i.user.id)
    async def vote(self, interaction: discord.Interaction,):
        """
        Get the link to the bot-vote Website.
        """
        await interaction.response.send_message(
                f"You can vote for {settings.bot_name} here: {settings.vote_link}\n"
                f"if you vote, you get a free {settings.collectible_name}. To see wich you get, join our Support Server\n"
                f"{settings.discord_invite} or just use /{settings.players_group_cog_name} last",
                ephemeral=True,
            )
        return
    
    @commands.Cog.listener()
    async def on_message(self, message,):
        """
        Give a random countryball as reward for Voting
        """
        if message.channel.id == settings.vote_hook_channel: # Webhook dir
            if message.content.startswith("r.votereward"):
                data = message.content.split(" ")
                sendchannel = self.bot.get_channel(settings.vote_reward_info_channel)
                special = None
                cob = await CountryBall.get_random()
                UserID = re.sub("\D", "", data[1])
                player, created = await Player.get_or_create(discord_id=UserID)
                instance = await BallInstance.create(
                    ball=cob.model,
                    player=player,
                    shiny=(random.randint(1, 2048) == 1),
                    attack_bonus=random.randint(-20, 20),
                    health_bonus=random.randint(-20, 20),
                    special=special,
                )
                extension = cob.model.wild_card.split(".")[-1]
                file_location = "." + cob.model.wild_card
                file_name = f"vote_reward_ball.{extension}"
                message = (
                    f"<@{UserID}> got a(n) **{instance.ball.country}** {settings.collectible_name}, because he/she sucecfully voted for {settings.bot_name}\n"
                    f"• ATK:`{instance.attack_bonus:+d}` • "
                    f"HP:`{instance.health_bonus:+d}` • Shiny: `{instance.shiny}`"
                )
                log.info(f"{UserID} got {instance.ball.country} for voting")
                await sendchannel.send(
                    message,
                    file=discord.File(file_location, filename=file_name),
                )
    
    @app_commands.command()
    @app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
    async def spawnalert(self, interaction: discord.Interaction, option: bool):
        """
        Add or remove the tag at the Spawn of an Countryball. - Made by GamingadlerHD
        Parameters
        ----------
        option: bool | None
            Select if you want to get taged at spawns
        """
        guild = interaction.guild
        spawn_ping_role_name = "SpawnPing"
        member = interaction.user
        spawn_ping_role = get(guild.roles, name=spawn_ping_role_name)
        if not spawn_ping_role:
            # Create the role if it doesn't exist
            spawn_ping_role = await guild.create_role(
                name=spawn_ping_role_name, reason="Creating SpawnPing role"
            )

        if option:
            # Create or retrieve the "SpawnPing" role
            await interaction.user.add_roles(spawn_ping_role, reason="Assigning SpawnPing role")
            await interaction.response.send_message(
                f"You will now be informed at the next {settings.collectible_name} spawn",
                ephemeral=True,
            )
            return

        else:
            # Remove the role if it exists
            await member.remove_roles(spawn_ping_role, reason="Removing SpawnPing role")
            await interaction.response.send_message(
                f"You will no longer be informed about {settings.collectible_name} spawns.",
                ephemeral=True,
            )
            return
    
    @app_commands.command()
    @app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
    async def rarity(self, interaction: discord.Interaction):
        # DO NOT CHANGE THE CREDITS TO THE AUTHOR HERE!
        """
        Show the rarity list of the dex - made by GamingadlerHD
        """
        # Filter enabled collectibles
        enabled_collectibles = [x for x in balls.values() if x.enabled]

        if not enabled_collectibles:
            await interaction.response.send_message(
                f"There are no collectibles registered in {settings.bot_name} yet.",
                ephemeral=True,
            )
            return

        # Sort collectibles by rarity in ascending order
        sorted_collectibles = sorted(enabled_collectibles, key=lambda x: x.rarity)

        entries = []

        for collectible in sorted_collectibles:
            name = f"{collectible.country}"
            emoji = self.bot.get_emoji(collectible.emoji_id)

            if emoji:
                emote = str(emoji)
            else:
                emote = "N/A"
            #if you want the Rarity to only show full numbers like 1 or 12 use the code part here:
            # rarity = int(collectible.rarity)
            # otherwise you want to display numbers like 1.5, 5.3, 76.9 use the normal part.
            rarity = collectible.rarity

            entry = (name, f"{emote} Rarity: {rarity}")
            entries.append(entry)
        # This is the number of countryballs who are displayed at one page, 
        # you can change this, but keep in mind: discord has an embed size limit.
        per_page = 5 

        source = FieldPageSource(entries, per_page=per_page, inline=False, clear_description=False)
        source.embed.description = (
            f"__**{settings.bot_name} rarity**__"
        )
        source.embed.colour = discord.Colour.blurple()
        source.embed.set_author(
            name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url
        )

        pages = Pages(source=source, interaction=interaction, compact=True)
        await pages.start()

    @app_commands.command()
    @app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
    async def events_rarity(self, interaction: discord.Interaction):
        # DO NOT CHANGE THE CREDITS TO THE AUTHOR HERE!
        """
        Show the rarity list of the dex - made by GamingadlerHD
        """
        # Filter enabled collectibles
        events = [x for x in specials.values()]

        if not events:
            await interaction.response.send_message(
                f"There are no events registered in {settings.bot_name} yet.",
                ephemeral=True,
            )
            return

        # Sort collectibles by rarity in ascending order
        

        entries = []

        for special in events:
            name = f"{special.name}"
            emoji = special.emoji

            if emoji:
                emote = str(emoji)
            else:
                emote = "N/A"
            
            filters = {} 
            filters["special"] = special

            count = await BallInstance.filter(**filters)
            countNum = len(count)
            #sorted_collectibles = sorted(enabled_collectibles.values(), key=lambda x: x.rarity)
            #if you want the Rarity to only show full numbers like 1 or 12 use the code part here:
            # rarity = int(collectible.rarity)
            # otherwise you want to display numbers like 1.5, 5.3, 76.9 use the normal part.
            

            entry = (name, f"{emote} Count: {countNum}")
            entries.append(entry)
        # This is the number of countryballs who are displayed at one page, 
        # you can change this, but keep in mind: discord has an embed size limit.
        per_page = 5 

        source = FieldPageSource(entries, per_page=per_page, inline=False, clear_description=False)
        source.embed.description = (
            f"__**{settings.bot_name} events rarity**__"
        )
        source.embed.colour = discord.Colour.blurple()
        source.embed.set_author(
            name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url
        )

        pages = Pages(source=source, interaction=interaction, compact=True)
        await pages.start()
