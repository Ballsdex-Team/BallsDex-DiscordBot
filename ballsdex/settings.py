import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import yaml

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
    wild_phrase: str
        The phrase used when a collectible spawns
    wrong_name_phrase: str
        The phrase used when a user enters the wrong name for that collectible
    you_caught_phrase: str
        The phrase used when a user catch a ball
    new_completion_phrase: str = ""
        The phrase used when a user caught a new collectible
    caught_already_phrase: str
        The phrase used when the collectible is caught already
    mention_user: bool
        An option to choose if wrong_name new_comp and caught_already should mention user
    """

    bot_token: str = ""
    gateway_url: str | None = None
    shard_count: int | None = None
    prefix: str = "b."

    collectible_name: str = "countryball"
    bot_name: str = "BallsDex"
    players_group_cog_name: str = "balls"
    wild_phrase: str = ""
    wrong_name_phrase: str = ""
    you_caught_phrase: str = ""
    new_completion_phrase: str = ""
    caught_already_phrase: str = ""
    mention_user: bool = True

    max_favorites: int = 50

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

    log_channel: int | None = None

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
    settings.prefix = str(content.get("text-prefix") or "b.")
    settings.team_owners = content.get("owners", {}).get("team-members-are-owners", False)
    settings.co_owners = content.get("owners", {}).get("co-owners", [])

    settings.collectible_name = content["collectible-name"]
    settings.bot_name = content["bot-name"]
    settings.players_group_cog_name = content["players-group-cog-name"]
    settings.wild_phrase = content.get("wild-phrase", "")
    settings.wrong_name_phrase = content.get("wrong-name-phrase", "Wrong name!")
    settings.you_caught_phrase = content.get("you-caught-phrase", "You caught {ball_name}!")
    settings.new_completion_phrase = content.get(
        "new-completion-phrase",
        "This is a **new {collectible_name}** that has been added to your completion!",
    )
    settings.caught_already_phrase = content.get("caught-already", "I was caught already!")
    settings.mention_user = bool(content.get("mention-user", True))

    settings.about_description = content["about"]["description"]
    settings.github_link = content["about"]["github-link"]
    settings.discord_invite = content["about"]["discord-invite"]
    settings.terms_of_service = content["about"]["terms-of-service"]
    settings.privacy_policy = content["about"]["privacy-policy"]

    settings.admin_guild_ids = content["admin-command"]["guild-ids"] or []
    settings.root_role_ids = content["admin-command"]["root-role-ids"] or []
    settings.admin_role_ids = content["admin-command"]["admin-role-ids"] or []

    settings.log_channel = content.get("log-channel", None)

    settings.prometheus_enabled = content["prometheus"]["enabled"]
    settings.prometheus_host = content["prometheus"]["host"]
    settings.prometheus_port = content["prometheus"]["port"]

    settings.max_favorites = content.get("max-favorites", 50)
    log.info("Settings loaded.")


def write_default_settings(path: "Path"):
    path.write_text(
        """# yaml-language-server: $schema=json-config-ref.json

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

# override the phrase "A wild {collectible_name} appeared!
# NOTE THAT you MUST include {collectible_name} somewhere in the phrase
wild-phrase: A wild {collectible_name} appeared!

# override the phrase "Wrong name!"
wrong-name-phrase: Wrong name!

# override the phrase "You caught {ball_name}!"
# NOTE THAT you MUST include {ball_name} somewhere in the phrase
you-caught-phrase: You caught {ball_name}!

# ↓↓↓↓↓↓↓↓↓↓↓↓↓↓ override the phrase ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
# "This is a **new {collectible_name}** that has been added to your completion!"
# NOTE THAT you MUST include {collectible_name} somewhere in the phrase
new-completion-phrase: This is a **new {collectible_name}** that has been added to your completion!

# override the phrase "I was caught already!"
caught-already-phrase: I was caught already!

# this is an option if it should mention the user in those phrases or not
# it will only show up first then the phrase
mention-user: true

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

# log channel for moderation actions
log-channel:

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
    add_config_ref = "# yaml-language-server: $schema=json-config-ref.json" not in content

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
    if add_config_ref:
        if "# yaml-language-server: $schema=config-ref.json" in content:
            # old file name replacement
            content = content.replace("$schema=config-ref.json", "$schema=json-config-ref.json")
        else:
            content = "# yaml-language-server: $schema=json-config-ref.json\n" + content

    if any((add_owners, add_config_ref)):
        path.write_text(content)
