import logging
import random
import sys
from typing import TYPE_CHECKING, Dict
from dataclasses import dataclass, field

import discord
from discord import app_commands
from discord.ext import commands

import asyncio
import io

from ballsdex.core.models import (
    Ball,
    BallInstance,
    Regime,
    Player as PlayerModel,
)
from ballsdex.core.utils.transformers import (
    BallInstanceTransform,
    BallEnabledTransform,
)
from ballsdex.core.utils.utils import inventory_privacy, is_staff
from ballsdex.core.models import balls as countryballs
from ballsdex.settings import settings


if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
log = logging.getLogger("ballsdex.packages.currency")

@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(dms=True, private_channels=True, guilds=True)
class Credits(commands.GroupCog, group_name="credits"):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.CostByRarity = {"rare": 160, "super_rare": 430, "epic": 925, "mythic": 1900, "legendary": 3800}
        self.ExcludeOptions = ["ultra_legendary",]
        
    @app_commands.command(name="show")
    @app_commands.checks.cooldown(3, 30, key=lambda i: i.user.id)
    async def credits_show(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
    ):
        """
        Show Credits.
        """
        user_obj = user or interaction.user
        await interaction.response.defer(thinking=True)
        playerm, _ = await PlayerModel.get_or_create(discord_id=user_obj.id)

        if playerm.credits == 0:
            if user_obj == interaction.user:
                await interaction.followup.send(
                    f"You do not have any credits, catch Brawlers to get credits!"
                )
            else:
                await interaction.followup.send(
                    f"{user_obj.name} doesn't have any credits yet."
                )
            return

        if user is not None:
            if await inventory_privacy(self.bot, interaction, playerm, user_obj) is False:
                return
        interaction_player = await PlayerModel.get(discord_id=interaction.user.id)

        blocked = await playerm.is_blocked(interaction_player)
        if blocked and not is_staff(interaction):
            await interaction.followup.send(
                "You cannot view the currency of a user that has you blocked.", ephemeral=True
            )
            return


        if user_obj == interaction.user:
            await interaction.followup.send(
                f"You have {playerm.credits} credits."
            )
        else:
            await interaction.followup.send(
                f"{user_obj.name} has {playerm.credits} credits."
            )


    @app_commands.command(name="info")
    @app_commands.checks.cooldown(1, 20, key=lambda i: i.channel.id)
    async def credits_info(
        self,
        interaction: discord.Interaction,
        
    ):
        """
        Show Credits Shop Prices
        """
        
        mjc = self.bot.get_emoji(1364877727601004634)
        mjrare = self.bot.get_emoji(1330493249235714189)
        mjsuperrare = self.bot.get_emoji(1330493410884456528)
        mjepic = self.bot.get_emoji(1330493427011555460)
        mjmythic = self.bot.get_emoji(1330493448469483580)
        mjlegendary = self.bot.get_emoji(1330493465221529713)
        mjultra = self.bot.get_emoji(1368271368382320761)
        embed = discord.Embed(
            title="Credits Info",
            description=f"{mjc} **Prices** {mjc} \n\nRare{mjrare}: 160{mjc} \nSuper Rare{mjsuperrare}: 430{mjc} \nEpic{mjepic}: 925{mjc} \nMythic{mjmythic}: 1900{mjc} \nLegendary{mjlegendary}: 3800{mjc} \n\n-# {mjultra} Ultra Legendaries are unpurchaseable.",
            color=discord.Color.og_blurple()
)       
        await interaction.response.send_message(embed=embed)


    @app_commands.command(name="claim")
    @app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
    async def credits_claim(
        self,
        interaction: discord.Interaction,
        brawler: BallEnabledTransform,
        
    ):
        """
        Claim a Brawler using Credits!
        
        Parameters
        ----------
        brawler: Ball
            The Brawler you want.
        """
        Reg = await Regime.get(id=brawler.regime_id)
        if Reg.name.lower().strip().replace(" ", "_") in self.ExcludeOptions:
            await interaction.response.send_message(f"{brawler.country} can not be claimed.",ephemeral=True)
            return
        if Reg.name.lower().strip().replace(" ", "_") not in self.CostByRarity:
            await interaction.response.send_message(f"Non-brawlers can not currently be claimed.",ephemeral=True)
            return
        
        playerm = await PlayerModel.get(discord_id=interaction.user.id)
        
        cost = self.CostByRarity[(await Regime.get(id=brawler.regime_id)).name.lower().strip().replace(" ", "_")]
        if cost is None:
            await interaction.response.send_message(f"{brawler.country} can not currently be claimed.",ephemeral=True)
            return
        if playerm.credits >= cost:
            await interaction.response.defer(thinking=True)
            playerm.credits -= cost
            await playerm.save(update_fields=("credits",))
            inst = await BallInstance.create(
                ball=brawler,
                player=playerm,
                attack_bonus=0,
                health_bonus=0,
                server_id=interaction.guild.id
            )
            data, file, view = await inst.prepare_for_message(interaction)
            try:
                await interaction.followup.send(interaction.user.mention+", your Brawler has been claimed.\n\n"+data, file=file, view=view)
            finally:
                file.close()
                log.debug(f"{interaction.user.id} claimed a {brawler.country}")       

@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(dms=True, private_channels=True, guilds=True)
class PowerPoints(commands.GroupCog, group_name="powerpoints"):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.NextUpgradeCost = {2: 20, 3: 30, 4: 50, 5: 80, 6: 130, 7: 210, 8: 340, 9: 550, 10: 890, 11: 1440}
        
    @app_commands.command(name="show")
    @app_commands.checks.cooldown(3, 30, key=lambda i: i.user.id)
    async def pp_show(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
    ):
        """
        Show Power Points.
        """
        user_obj = user or interaction.user
        await interaction.response.defer(thinking=True)
        playerm, _ = await PlayerModel.get_or_create(discord_id=user_obj.id)

        if playerm.powerpoints == 0:
            if user_obj == interaction.user:
                await interaction.followup.send(
                    f"You do not have any power points, catch Brawlers to get power points!"
                )
            else:
                await interaction.followup.send(
                    f"{user_obj.name} doesn't have any power points yet."
                )
            return

        if user is not None:
            if await inventory_privacy(self.bot, interaction, playerm, user_obj) is False:
                return
        interaction_player = await PlayerModel.get(discord_id=interaction.user.id)

        blocked = await playerm.is_blocked(interaction_player)
        if blocked and not is_staff(interaction):
            await interaction.followup.send(
                "You cannot view the currency of a user that has you blocked.", ephemeral=True
            )
            return


        if user_obj == interaction.user:
            await interaction.followup.send(
                f"You have {playerm.powerpoints} power points."
            )
        else:
            await interaction.followup.send(
                f"{user_obj.name} has {playerm.powerpoints} power points."
            )


    @app_commands.command(name="shop")
    @app_commands.checks.cooldown(1, 20, key=lambda i: i.channel.id)
    async def pp_chart(
        self,
        interaction: discord.Interaction,
        
    ):
        """
        Show Power Points Leveling Chart
        """
        
        mj = self.bot.get_emoji(1364807487106191471)
        embed = discord.Embed(
            title="Power Points Shop",
            description=f"Power Level 2: 20{mj} (Total: 20)\nPower Level 3: 30{mj} (Total: 50)\nPower Level 4: 50{mj} (Total: 100)\nPower Level 5: 80{mj} (Total: 180)\nPower Level 6: 130{mj} (Total: 310)\nPower Level 7: 210{mj} (Total: 520)\nPower Level 8: 340{mj} (Total: 860)\nPower Level 9: 550{mj} (Total: 1410)\nPower Level 10: 890{mj} (Total: 2300)\nPower Level 11: 1440{mj} (Total: 3740)\n\nNote: Each power level gives a +10% stat boost.",
            color=discord.Color.pink()
)       
        await interaction.response.send_message(embed=embed)


    @app_commands.command(name="upgrade")
    @app_commands.checks.cooldown(2, 60, key=lambda i: i.user.id)
    async def pp_upgrade(
        self,
        interaction: discord.Interaction,
        brawler: BallInstanceTransform,
        
    ):
        """
        Upgrade a Brawler to the next Power Level.
        
        Parameters
        ----------
        brawler: BallInstance
            The Brawler you want to Upgrade.
        """
        playerm = await PlayerModel.get(discord_id=interaction.user.id)
        
        plvl = int((brawler.health_bonus+brawler.attack_bonus+20)/20+1)
        cost = self.NextUpgradeCost[plvl]
        if brawler.health_bonus >= 100 and brawler.attack_bonus >= 100 or cost is None:
            await interaction.response.send_message("This brawler can not be upgraded further.", ephemeral=True)
        elif playerm.powerpoints >= cost:
            await interaction.response.defer(thinking=True)
            playerm.powerpoints -= cost
            await playerm.save(update_fields=("powerpoints",))
            brawler.health_bonus += 10; brawler.attack_bonus += 10
            await brawler.save()
            data, file, view = await brawler.prepare_for_message(interaction)
            try:
                await interaction.followup.send(interaction.user.mention+", your Brawler has been upgraded.\n\n"+data, file=file, view=view)
            finally:
                file.close()
                log.debug(f"{interaction.user.id} upgraded a {brawler.id}")


@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(dms=True, private_channels=True, guilds=True)
class Currency(commands.Cog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.CurrencyPortion = {"powerpoints": 30, "credits": 45}


    @app_commands.command(name="freebie")
    @app_commands.checks.cooldown(1, 86400, key=lambda i: i.user.id)
    async def daily_freebie(
        self,
        interaction: discord.Interaction,
        
    ):
        """
        Claim your daily freebie.
        """
        options = ["powerpoints", "credits", "powerpoints10", "credits10"]
        chances = [96, 96, 4, 4]

        choice = random.choices(options, weights=chances, k=1)[0]
        
        player, _ = await PlayerModel.get_or_create(discord_id=interaction.user.id)  
        await interaction.response.defer(thinking=True)    
        cmnt = self.CurrencyPortion[choice.replace("10", "")] 
        jackpot = choice        
        if "10" in choice:
            choice = choice.replace("10", "")
            jackpot = jackpot.replace("10", ", You hit the Jackpot, You get 10x the reward!")
            cmnt *= 10
        setattr(player, choice, getattr(player, choice) + cmnt)
        await player.save(update_fields=(choice,))
        await interaction.followup.send(f"You received your {cmnt} {jackpot}", ephemeral=True)
