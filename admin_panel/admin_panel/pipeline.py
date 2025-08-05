from enum import Enum
from typing import TYPE_CHECKING, Literal

import aiohttp
from asgiref.sync import async_to_sync, sync_to_async
from bd_models.models import (
    Ball,
    BallInstance,
    BlacklistedGuild,
    BlacklistedID,
    BlacklistHistory,
    Block,
    Economy,
    Friendship,
    GuildConfig,
    Player,
    Regime,
    Special,
    Trade,
    TradeObject,
)
from django.contrib import messages
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from ballsdex.settings import settings

from .webhook import notify_admins

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from django.db.models import Model
    from django.http import HttpRequest
    from social_core.backends.base import BaseAuth

type perm_dict = dict[
    "type[Model]", list[Literal["view", "add", "change", "delete"]] | Literal["*"]
]

DISCORD_API = "https://discord.com/api/v10/"


class Status(Enum):
    STAFF = 0  # has a role in the "admin-role-ids" of config.yml
    ADMIN = 1  # has a role in the "root-role-ids" of config.yml
    TEAM_MEMBER = 2  # is a member of the Discord team owning the application
    CO_OWNER = 3  # has its ID in the "co-owners" section of config.yml
    OWNER = 4  # owns the application


async def get_permissions(permissions: perm_dict) -> list[Permission]:
    """
    Returns the list of permissions objects from a dictionnary mapping models to permission codes.
    """
    result: list[Permission] = []
    for model, perms in permissions.items():
        content_type = await sync_to_async(ContentType.objects.get_for_model)(model)
        if perms == "*":
            perms = ["add", "change", "delete", "view"]
        for perm in perms:
            result.append(
                await Permission.objects.aget(
                    content_type=content_type, codename=f"{perm}_{model._meta.model_name}"
                )
            )
    return result


async def assign_status(request: "HttpRequest", response: dict, user: "User", status: Status):
    """
    Assign the correct attributes and groups to the user based on the given status.
    A message will be displayed to the user.
    """
    notify = not user.is_staff

    user.is_staff = True
    if status == Status.STAFF:
        user.is_superuser = False
        group, created = await Group.objects.aget_or_create(name="Staff")
        if created:
            perms: perm_dict = {
                BallInstance: ["view"],
                BlacklistedGuild: "*",
                BlacklistedID: "*",
                BlacklistHistory: ["view"],
                Block: "*",
                Friendship: "*",
                GuildConfig: ["view", "change"],
                Player: ["view", "change"],
                Trade: ["view"],
                TradeObject: ["view"],
            }
            await group.permissions.aadd(*await get_permissions(perms))
        await user.groups.aadd(group)
        message = "You were assigned the Staff status because of your Discord roles."
    elif status == Status.ADMIN:
        user.is_superuser = False
        group, created = await Group.objects.aget_or_create(name="Admin")
        if created:
            perms: perm_dict = {
                Ball: "*",
                Regime: "*",
                Economy: "*",
                Special: "*",
                BallInstance: "*",
                BlacklistedGuild: "*",
                BlacklistedID: "*",
                BlacklistHistory: ["view"],
                Block: "*",
                Friendship: "*",
                GuildConfig: "*",
                Player: "*",
                Trade: ["view"],
                TradeObject: ["view"],
            }
            await group.permissions.aadd(*await get_permissions(perms))
        await user.groups.aadd(group)
        message = "You were assigned the Admin status because of your Discord roles."
    elif status == Status.TEAM_MEMBER:
        user.is_superuser = True
        message = (
            "You were assigned the superuser status because you are a team member, "
            "and the bot is configured to treat team members as owners."
        )
    elif status == Status.CO_OWNER:
        user.is_superuser = True
        message = "You were assigned the superuser status because you are a co-owner in config.yml"
    elif status == Status.OWNER:
        user.is_superuser = True
        message = (
            "You were assigned the superuser status because you are the owner of the application."
        )
    else:
        raise ValueError(f"Unknown status: {status}")
    await user.asave()

    if notify:
        messages.success(request, message)
        await notify_admins(
            f"{response['global_name']} (`{response['username']}`, {response['id']}) has been "
            f"assigned the {status.name} status on the admin panel."
        )


@async_to_sync
async def configure_status(
    request: "HttpRequest", backend: "BaseAuth", user: "User", uid: str, response: dict, **kwargs
):
    if backend.name != "discord":
        return
    if response["mfa_enabled"] is False:
        messages.error(
            request, "You cannot use an account without multi-factor authentication enabled."
        )
        return
    discord_id = int(uid)

    # check if user is a co-owner in config.yml (no API call required)
    if settings.co_owners and discord_id in settings.co_owners:
        await assign_status(request, response, user, Status.CO_OWNER)
        return

    headers = {"Authorization": f"Bot {settings.bot_token}"}
    async with aiohttp.ClientSession(
        base_url=DISCORD_API, headers=headers, raise_for_status=True
    ) as session:

        # check if user owns the application, or is part of the team and team members are co owners
        async with session.get("applications/@me") as resp:
            info = await resp.json()
            if info["owner"]["id"] == uid or (
                info["team"] and info["team"]["owner_user_id"] == uid
            ):
                await assign_status(request, response, user, Status.OWNER)
                return
            if (
                settings.team_owners
                and info["team"]
                and uid in (x["user"]["id"] for x in info["team"]["members"])
            ):
                await assign_status(request, response, user, Status.TEAM_MEMBER)
                return

        # no admin guild configured, no roles, nothing to do
        if not settings.admin_guild_ids or not (settings.admin_role_ids or settings.root_role_ids):
            return

        # check if the user owns roles configured as root/admin in config.yml
        session.headers["Authorization"] = f"Bearer {response['access_token']}"
        async with session.get("users/@me/guilds") as resp:
            guilds = await resp.json()

        for guild in guilds:
            if int(guild["id"]) not in settings.admin_guild_ids:
                continue
            async with session.get(f"users/@me/guilds/{guild['id']}/member") as resp:
                member = await resp.json()

            # If we find the user with an "admin" role, we must keep iterating in case a "root"
            # role is found later. If a "root" role is found, we can immediately stop and assign
            is_staff = False
            for role in member["roles"]:
                if settings.root_role_ids and int(role) in settings.root_role_ids:
                    await assign_status(request, response, user, Status.ADMIN)
                    return
                elif settings.admin_role_ids and int(role) in settings.admin_role_ids:
                    is_staff = True
            if is_staff:
                await assign_status(request, response, user, Status.STAFF)
                return

    # If we reached this point, the user has no administration role.
    # A user object will have been created, but without is_staff, the admin panel will be blocked.
    # It could also be an ex-staff member logging in, which must be handled manually
    if user.is_staff or user.is_superuser:
        await notify_admins(
            f"{response['global_name']} (`{response['username']}`, {response['id']}) logged in to "
            "the admin panel using Discord OAuth2, but no staff status has been found. "
            f"{user.is_staff=} {user.is_superuser=}"
        )
