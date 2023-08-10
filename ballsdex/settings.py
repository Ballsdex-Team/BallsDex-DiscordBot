import yaml
import logging

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

log = logging.getLogger("ballsdex.settings")


@dataclass
class Settings:
    """
    Global bot settings

    Attributes
    ----------
    bot_token: str
        Discord token for the bot to connect
    gateway_url: str | None
        The URL of the Discord gateway that this instance of the bot should connect to and use.
    shard_count: int | None
        The number of shards to use for this bot instance.
        Must be equal to the one set in the gateway proxy if used.
    prefix: str
        Prefix for text commands, mostly unused. Defaults to "b."
    collectible_name: str
        Usually "countryball", can be replaced when possible
    bot_name: str
        Usually "BallsDex", can be replaced when possible
    players_group_cog_name: str
        Set the name of the base command of the "players" cog, /balls by default
    about_description: str
        Used in the /about command
    github_link: str
        Used in the /about command
    discord_invite: str
        Used in the /about command
    terms_of_service: str
        Used in the /about command
    privacy_policy: str
        Used in the /about command
    admin_guild_ids: list[int]
        List of guilds where the /admin command must be registered
    root_role_ids: list[int]
        List of roles that have full access to the /admin command
    admin_role_ids: list[int]
        List of roles that have partial access to the /admin command (only blacklist and guilds)
    """

    bot_token: str = ""
    gateway_url: str | None = None
    shard_count: int | None = None
    prefix: str = "b."

    collectible_name: str = "countryball"
    bot_name: str = "BallsDex"
    players_group_cog_name: str = "balls"

    # /about
    about_description: str = ""
    github_link: str = ""
    discord_invite: str = ""
    terms_of_service: str = ""
    privacy_policy: str = ""

    # /admin
    admin_guild_ids: list[int] = field(default_factory=list)
    root_role_ids: list[int] = field(default_factory=list)
    admin_role_ids: list[int] = field(default_factory=list)

    team_owners: bool = False
    co_owners: list[int] = field(default_factory=list)

    # metrics and prometheus
    prometheus_enabled: bool = False
    prometheus_host: str = "0.0.0.0"
    prometheus_port: int = 15260


settings = Settings()


def read_settings(path: "Path"):
    content = yaml.load(path.read_text(), yaml.Loader)

    settings.bot_token = content["discord-token"]
    settings.gateway_url = content.get("gateway-url")
    settings.shard_count = content.get("shard-count")
    settings.prefix = content["text-prefix"]
    settings.team_owners = content.get("owners", {}).get("team-members-are-owners", False)
    settings.co_owners = content.get("owners", {}).get("co-owners", [])

    settings.collectible_name = content["collectible-name"]
    settings.bot_name = content["bot-name"]
    settings.players_group_cog_name = content["players-group-cog-name"]

    settings.about_description = content["about"]["description"]
    settings.github_link = content["about"]["github-link"]
    settings.discord_invite = content["about"]["discord-invite"]
    settings.terms_of_service = content["about"]["terms-of-service"]
    settings.privacy_policy = content["about"]["privacy-policy"]

    settings.admin_guild_ids = content["admin-command"]["guild-ids"] or []
    settings.root_role_ids = content["admin-command"]["root-role-ids"] or []
    settings.admin_role_ids = content["admin-command"]["admin-role-ids"] or []

    settings.prometheus_enabled = content["prometheus"]["enabled"]
    settings.prometheus_host = content["prometheus"]["host"]
    settings.prometheus_port = content["prometheus"]["port"]
    log.info("Settings loaded.")


def write_default_settings(path: "Path"):
    path.write_text(
        """# yaml-language-server: $schema=config-ref.json

# paste the bot token after regenerating it here
discord-token: 

# prefix for old-style text commands, mostly unused
text-prefix: b.

# define the elements given with the /about command
about:

  # define the beginning of the description of /about
  # the other parts is automatically generated
  description: >
    Collect countryballs on Discord, exchange them and battle with friends!

  # override this if you have a fork
  github-link: https://github.com/laggron42/BallsDex-DiscordBot

  # valid invite for a Discord server
  discord-invite: https://discord.gg/ballsdex  # BallsDex official server

  terms-of-service: https://gist.github.com/laggron42/52ae099c55c6ee1320a260b0a3ecac4e
  privacy-policy: https://gist.github.com/laggron42/1eaa122013120cdfcc6d27f9485fe0bf

# WORK IN PROGRESS, DOES NOT FULLY WORK
# override the name "countryballs" in the bot
collectible-name: countryball

# WORK IN PROGRESS, DOES NOT FULLY WORK
# override the name "BallsDex" in the bot
bot-name: BallsDex

# players group cog command name
# this is /balls by default, but you can change it for /animals or /rocks for example
players-group-cog-name: balls

# enables the /admin command
admin-command:

  # all items here are list of IDs. example on how to write IDs in a list:
  # guild-ids:
  #   - 1049118743101452329
  #   - 1078701108500897923

  # list of guild IDs where /admin should be registered
  guild-ids:

  # list of role IDs having full access to /admin
  root-role-ids:

  # list of role IDs having partial access to /admin
  admin-role-ids:

# manage bot ownership
owners:
  # if enabled and the application is under a team, all team members will be considered as owners
  team-members-are-owners: false

  # a list of IDs that must be considered owners in addition to the application/team owner
  co-owners:

# prometheus metrics collection, leave disabled if you don't know what this is
prometheus:
  enabled: false
  host: "0.0.0.0"
  port: 15260
  """  # noqa: W291
    )


def update_settings(path: "Path"):
    content = path.read_text()

    add_owners = True

    for line in content.splitlines():
        if line.startswith("owners:"):
            add_owners = False

    if add_owners:
        content += """
# manage bot ownership
owners:
  # if enabled and the application is under a team, all team members will be considered as owners
  team-members-are-owners: false

  # a list of IDs that must be considered owners in addition to the application/team owner
  co-owners:
"""

    if any((add_owners,)):
        path.write_text(content)
