# this code was written by uint128-t.
# feel free to yell at me for this mess.
# add crafting to the bot
# configure it yourself noob, it won't work out of the box

import discord
from ballsdex.core.bot import BallsDexBot
from ballsdex.core.models import BallInstance,Player,Special,Ball
from discord import app_commands
from discord.ext import commands

from ballsdex.core.utils.sorting import sort_balls,SortingChoices
from ballsdex.packages.balls.countryballs_paginator import CountryballsSelector
from ballsdex.settings import settings

tiers = { # tier: required, previous
    9:(None,None),
    10:(2,9),
    11:(2,10),
    12:(2,11),
    13:(2,12),
    14:(2,13),
    15:(2,14),
}
regimec = { # if required is nonexistent instead it will be sourced from the regime of the ball
    5:10,
    22:10,
    6:8,
    23:8,
    7:5,
    24:5,
    8:3,
    25:3,
    16:2,
    26:2
}
allowed_regimes = {5,22,6,23,7,24,8,25,16,26} # you can only craft balls in these regimes

class CountryballsCrafter(CountryballsSelector):
    async def ball_selected(self, interaction: discord.Interaction, ball_instance: BallInstance):
        raise NotImplementedError()
    
    async def update(self):
        await self.show_page(self.original_interaction,self.current_page)

    @discord.ui.select()
    async def select_ball_menu(self, interaction: discord.Interaction, item: discord.ui.Select):
        await interaction.response.defer() # do not think
        ball_instance = await BallInstance.get(
            id=int(interaction.data.get("values")[0])  # type: ignore
        )
        await self.ball_selected(interaction, ball_instance)
    
    async def generate_content(self):
        raise NotImplementedError()
    
    async def show_page(self, interaction: discord.Interaction, page_number: int) -> None:
        page = await self.source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        self._update_labels(page_number)
        if kwargs is not None:
            if interaction.response.is_done():
                await interaction.followup.edit_message(
                    "@original", **kwargs,content=await self.generate_content(), view=self  # type: ignore
                )
            else:
                await interaction.response.edit_message(**kwargs, view=self)
    
    @discord.ui.button(label="Remove", style=discord.ButtonStyle.red)
    async def pop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.rm()
        await interaction.response.defer()
        await self.update()

    @discord.ui.button(label="Craft", style=discord.ButtonStyle.green,emoji="🛠️")
    async def craft(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.docraft(interaction)
    
    async def docraft(self,interaction:discord.Interaction):
        raise NotImplementedError()

    def fill_items(self):
        super().fill_items()
        self.pop.row = self.stop_pages.row
        self.craft.row = self.stop_pages.row
        self.add_item(self.pop)
        self.add_item(self.craft)
    
    async def rm(self):
        raise NotImplementedError()

async def getspname(sp:int):
    if sp==None:
        return ""
    else:
        return (await Special.get(pk=sp)).name+" "

class CraftingSession:
    def __init__(self,interaction:discord.Interaction["BallsDexBot"],bot:BallsDexBot,spec:int,ball:int):
        self.interaction=interaction
        self.bot = bot
        self.selectedS:set[BallInstance] = set()
        self.selectedL:list[BallInstance] = []
        self.spec = spec
        self.ball = ball
        self.spr,self.sp = tiers[spec]
    async def create(self):
        if not self.spr:
            self.spr = regimec[(await Ball.get(pk=self.ball)).regime_id]
        self.ballname = (await Ball.get(pk=self.ball)).country
        self.spname = await getspname(self.sp)
        self.bspname = f"**{(await Special.get(pk=self.sp)).name}** " if self.spname else ""
        self.specname = await getspname(self.spec)
        player, _ = await Player.get_or_create(discord_id=self.interaction.user.id)
        self.player = player
        await player.fetch_related("balls")
        query = player.balls.all()
        query = query.filter(special_id=self.sp)
        query = query.filter(ball_id=self.ball)
        query = query.order_by("-catch_date")
        if not await query.count():
            await self.interaction.response.send_message(f"You do not have any {self.bspname}{self.ballname} to craft this.")
            return
        self.selector=CountryballsCrafter(self.interaction,await query)
        self.selector.ball_selected = self.select # ultra cursed
        self.selector.generate_content = self.content # ultra cursed
        self.selector.pop.disabled = not self.selectedL
        self.selector.rm = self.pop # ultra cursed
        self.selector.docraft = self.craft # ultra cursed
        await self.selector.start(content=await self.content())
    async def select(self,interaction:discord.Interaction,ball_instance:BallInstance):
        # ultra cursed
        # self = crafter.crafting # ultra cursed
        if ball_instance not in self.selectedS:
            self.selectedL.append(ball_instance)
            self.selectedS.add(ball_instance)
        self.selector.pop.disabled = not self.selectedL
        await self.selector.update()
    async def content(self):
        c = []
        for ball in self.selectedL:
            emoji = self.bot.get_emoji(int(ball.countryball.emoji_id))
            favorite = f"{settings.favorited_collectible_emoji} " if ball.favorite else ""
            special = ball.special_emoji(self.bot, True)
            c.append(f"- {emoji}{favorite}{special}#{ball.pk:0X} {ball.countryball.country} `(Power Level {int((ball.health_bonus + 10) / 10)})`")
        await self.result()
        return f"## Crafting a {self.specname}{self.ballname}\nSelect {self.spr}x {self.bspname}{self.ballname} to craft\n{'\n'.join(c)}"
    async def result(self):
        self.selector.craft.disabled = len(self.selectedL)!=self.spr
    async def pop(self):
        self.selectedS.remove(self.selectedL.pop())
        self.selector.pop.disabled = not self.selectedL
    async def craft(self,interaction:discord.Interaction):
        assert len(self.selectedL)==self.spr
        player,_ = await Player.get_or_create(discord_id=interaction.user.id)
        np,_ = await Player.get_or_create(discord_id=self.bot.user.id) # type: ignore
        for b in self.selectedL:
            await b.refresh_from_db()
            if b.player_id != player.pk: # type: ignore
                await interaction.response.send_message(f"You do not own all of the selected {settings.plural_collectible_name}.")
                return
        for b in self.selectedL[1:]:
            b.trade_player_id = b.player_id # type: ignore
            b.player_id = np.pk
            await b.save()
        new = self.selectedL[0]
        new.special_id = self.spec
        await new.save()
        for item in self.selector.children:
            item.disabled = True  # type: ignore
        await interaction.response.edit_message(view=self.selector)
        self.selector.stop()
        emoji = self.bot.get_emoji(int(new.countryball.emoji_id))
        favorite = f"{settings.favorited_collectible_emoji} " if new.favorite else ""
        special = new.special_emoji(self.bot, True)
        await interaction.followup.send(f"Crafted a {emoji}{favorite}{special}#{new.pk:0X} **{self.specname}**{self.ballname}! `(Power Level {int((new.attack_bonus + 10) / 10)}))`")

class QuickCraftingSession(CraftingSession):
    async def create(self):
        if not self.spr:
            self.spr = regimec[(await Ball.get(pk=self.ball)).regime_id]
        player,_ = await Player.get_or_create(discord_id=self.interaction.user.id)
        await player.fetch_related("balls")

        fq = player.balls.all()
        fq = fq.filter(special_id=self.sp)
        fq = fq.filter(ball_id=self.ball)
        fq = fq.filter(favorite=False)
        fq = fq.order_by("-health_bonus")
        fq = fq.limit(1)
        async for bi in fq:
            self.selectedL.append(bi)
            self.selectedS.add(bi)

        query = player.balls.all()
        query = query.filter(special_id=self.sp)
        query = query.filter(ball_id=self.ball)
        query = query.filter(favorite=False)
        query = query.order_by("-catch_date")
        query = query.limit(self.spr)
        i = self.spr-1
        async for bi in query:
            if bi in self.selectedS:
                continue # !!!!
            self.selectedL.append(bi)
            self.selectedS.add(bi)
            i-=1
            if i==0:
                break
        await super().create()

async def type_autocomplete(interaction:discord.Interaction["BallsDexBot"],current:str):
    x = []
    i=25
    for t in tiers:
        sp = await Special.get(pk=t)
        if current.lower() in sp.name.lower():
            x.append(app_commands.Choice(name=sp.name,value=t))
            i-=1
        if i==0:
            break
    return x

async def ball_autocomplete(interaction:discord.Interaction["BallsDexBot"],current:str):
    # list all balls in current type
    b = Ball.all()
    b=b.filter(regime_id__in=allowed_regimes)
    x = []
    i=25
    async for ball in b:
        if current.lower() in ball.country.lower():
            x.append(app_commands.Choice(name=ball.country,value=ball.pk))
            i-=1
        if i==0:
            break
    return x

@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(dms=True, private_channels=True, guilds=True)
class Fame(commands.GroupCog):
    def __init__(self,bot:BallsDexBot):
        self.bot=bot
    @app_commands.command(name="begin",description=f"Craft a {settings.collectible_name}")
    @app_commands.describe(fame=f"The fame to craft")
    @app_commands.describe(brawler=f"Which {settings.collectible_name} to craft")
    @app_commands.describe(quick=f"Automatically load the last 10 non-favorited {settings.plural_collectible_name} for quick crafting")
    @app_commands.autocomplete(fame=type_autocomplete)
    @app_commands.autocomplete(brawler=ball_autocomplete)
    async def begin(self,interaction:discord.Interaction["BallsDexBot"],fame:int,brawler:int,quick:bool=False):
        spec = fame
        ball = brawler
        if spec not in tiers:
            await interaction.response.send_message(f"Invalid {settings.collectible_name} type.")
            return
        b = await Ball.get(pk=ball)
        if b.regime_id not in allowed_regimes:
            await interaction.response.send_message(f"You are not allowed to craft {b.country}.")
            return
        if quick:
            await QuickCraftingSession(interaction,self.bot,spec,ball).create()
        else:
            await CraftingSession(interaction,self.bot,spec,ball).create()
       

async def setup(bot:BallsDexBot):
    await bot.add_cog(Fame(bot))
