import os
from typing import Any, List

from fastapi_admin.app import app
from fastapi_admin.enums import Method
from fastapi_admin.file_upload import FileUpload
from fastapi_admin.resources import Action, Field, Link, Model
from fastapi_admin.widgets import displays, filters, inputs
from starlette.requests import Request

from ballsdex.core.models import (
    Ball,
    BallInstance,
    BlacklistedGuild,
    BlacklistedID,
    Economy,
    GuildConfig,
    Player,
    Regime,
    Special,
    User,
)


@app.register
class Home(Link):
    label = "Home"
    icon = "fas fa-home"
    url = "/admin"


upload = FileUpload(uploads_dir=os.path.join(".", "static", "uploads"))


@app.register
class AdminResource(Model):
    label = "Admin"
    model = User
    icon = "fas fa-user"
    page_pre_title = "admin list"
    page_title = "Admins"
    filters = [
        filters.Search(
            name="username",
            label="Name",
            search_mode="contains",
            placeholder="Search for username",
        ),
    ]
    fields = [
        "id",
        "username",
        Field(
            name="password",
            label="Password",
            display=displays.InputOnly(),
            input_=inputs.Password(),
        ),
        Field(
            name="avatar",
            label="Avatar",
            display=displays.Image(width="40"),
            input_=inputs.Image(null=True, upload=upload),
        ),
        "created_at",
    ]

    async def cell_attributes(self, request: Request, obj: dict, field: Field) -> dict:
        if field.name == "id":
            return {"class": "bg-danger text-white"}
        return await super().cell_attributes(request, obj, field)


@app.register
class SpecialResource(Model):
    label = "Special events"
    model = Special
    icon = "fas fa-star"
    page_pre_title = "special list"
    page_title = "Special events list"
    filters = [
        filters.Search(
            name="name", label="Name", search_mode="icontains", placeholder="Search for events"
        ),
        filters.Boolean(name="hidden", label="Hidden"),
    ]
    fields = [
        "name",
        "catch_phrase",
        Field(
            name="start_date",
            label="Start date of the event",
            display=displays.DateDisplay(),
            input_=inputs.Date(help_text="Date when special balls will start spawning"),
        ),
        Field(
            name="end_date",
            label="End date of the event",
            display=displays.DateDisplay(),
            input_=inputs.Date(help_text="Date when special balls will stop spawning"),
        ),
        "rarity",
        Field(
            name="background",
            label="Special background (1428x2000)",
            display=displays.Image(width="40"),
            input_=inputs.Image(upload=upload, null=True),
        ),
        "emoji",
        "tradeable",
        "hidden",
    ]

    async def get_actions(self, request: Request) -> List[Action]:
        actions = await super().get_actions(request)
        actions.append(
            Action(
                icon="fas fa-upload",
                label="Generate card",
                name="generate",
                method=Method.GET,
                ajax=False,
            )
        )
        return actions


@app.register
class RegimeResource(Model):
    label = "Regime"
    model = Regime
    icon = "fas fa-flag"
    page_pre_title = "regime list"
    page_title = "Regimes"
    fields = [
        "name",
        Field(
            name="background",
            label="Background (1428x2000)",
            display=displays.Image(width="40"),
            input_=inputs.Image(upload=upload, null=True),
        ),
    ]


@app.register
class EconomyResource(Model):
    label = "Economy"
    model = Economy
    icon = "fas fa-coins"
    page_pre_title = "economy list"
    page_title = "Economies"
    fields = [
        "name",
        Field(
            name="icon",
            label="Icon (512x512)",
            display=displays.Image(width="40"),
            input_=inputs.Image(upload=upload, null=True),
        ),
    ]


class Emoji(displays.Display):
    async def render(self, request: Request, value: Any):
        return (
            f'<img src="https://cdn.discordapp.com/emojis/{value}.png?size=40" '
            f'title="ID: {value}" />'
        )


@app.register
class BallResource(Model):
    label = "Ball"
    model = Ball
    page_size = 50
    icon = "fas fa-globe"
    page_pre_title = "ball list"
    page_title = "Balls"
    filters = [
        filters.Search(
            name="country",
            label="Country",
            search_mode="icontains",
            placeholder="Search for balls",
        ),
        filters.ForeignKey(model=Regime, name="regime", label="Regime"),
        filters.ForeignKey(model=Economy, name="economy", label="Economy"),
        filters.Boolean(name="enabled", label="Enabled"),
        filters.Boolean(name="tradeable", label="Tradeable"),
    ]
    fields = [
        "country",
        "short_name",
        "catch_names",
        "translations",
        "created_at",
        "regime",
        "economy",
        "health",
        "attack",
        "rarity",
        "enabled",
        "tradeable",
        Field(
            name="emoji_id",
            label="Emoji",
            display=Emoji(),
        ),
        Field(
            name="wild_card",
            label="Wild card",
            display=displays.Image(width="40"),
            input_=inputs.Image(upload=upload, null=True),
        ),
        Field(
            name="collection_card",
            label="Collection card (16:9 ratio)",
            display=displays.Image(width="40"),
            input_=inputs.Image(upload=upload, null=True),
        ),
        Field(
            name="credits",
            label="Image credits",
        ),
        Field(
            name="capacity_name",
            label="Capacity name",
        ),
        Field(
            name="capacity_description",
            label="Capacity description",
        ),
    ]

    async def get_actions(self, request: Request) -> List[Action]:
        actions = await super().get_actions(request)
        actions.append(
            Action(
                icon="fas fa-upload",
                label="Generate card",
                name="generate",
                method=Method.GET,
                ajax=False,
            )
        )
        return actions


@app.register
class BallInstanceResource(Model):
    label = "Ball instance"
    model = BallInstance
    icon = "fas fa-atlas"
    page_pre_title = "ball instances list"
    page_title = "Ball instances"
    filters = [
        filters.Search(
            name="id",
            label="Ball Instance ID",
            placeholder="Search for ball IDs",
        ),
        filters.ForeignKey(model=Ball, name="ball", label="Ball"),
        filters.ForeignKey(model=Special, name="special", label="Special"),
        filters.Boolean(name="shiny", label="Shiny"),
        filters.Boolean(name="favorite", label="Favorite"),
        filters.Search(
            name="player__discord_id",
            label="User ID",
            placeholder="Search for Discord user ID",
        ),
        filters.Search(
            name="server_id",
            label="Server ID",
            placeholder="Search for Discord server ID",
        ),
        filters.Boolean(name="tradeable", label="Tradeable"),
    ]
    fields = [
        "id",
        "ball",
        "player",
        "catch_date",
        "server_id",
        "shiny",
        "special",
        "favorite",
        "health_bonus",
        "attack_bonus",
        "tradeable",
    ]


@app.register
class PlayerResource(Model):
    label = "Player"
    model = Player
    icon = "fas fa-user"
    page_pre_title = "player list"
    page_title = "Players"
    filters = [
        filters.Search(
            name="discord_id",
            label="ID",
            search_mode="icontains",
            placeholder="Filter by ID",
        ),
    ]
    fields = [
        "discord_id",
        "balls",
        "donation_policy",
        "privacy_policy",
    ]


@app.register
class GuildConfigResource(Model):
    label = "Guild config"
    model = GuildConfig
    icon = "fas fa-cog"
    page_title = "Guild configs"
    filters = [
        filters.Search(
            name="guild_id",
            label="ID",
            search_mode="icontains",
            placeholder="Filter by ID",
        ),
    ]
    fields = ["guild_id", "spawn_channel", "enabled", "silent"]


@app.register
class BlacklistedIDResource(Model):
    label = "Blacklisted user ID"
    model = BlacklistedID
    icon = "fas fa-user-lock"
    page_title = "Blacklisted user IDs"
    filters = [
        filters.Search(
            name="discord_id",
            label="ID",
            search_mode="icontains",
            placeholder="Filter by ID",
        ),
        filters.Search(
            name="reason",
            label="Reason",
            search_mode="search",
            placeholder="Search by reason",
        ),
    ]
    fields = [
        "discord_id",
        "reason",
    ]


@app.register
class BlacklistedGuildIDResource(Model):
    label = "Blacklisted Guild ID"
    model = BlacklistedGuild
    icon = "fas fa-lock"
    page_title = "Blacklisted Guild IDs"
    filters = [
        filters.Search(
            name="guild_id",
            label="ID",
            search_mode="icontains",
            placeholder="Filter by Guild ID",
        ),
        filters.Search(
            name="reason",
            label="Reason",
            search_mode="search",
            placeholder="Search by reason",
        ),
    ]
    fields = [
        "discord_id",
        "reason",
    ]
