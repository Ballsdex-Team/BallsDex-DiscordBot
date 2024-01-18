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
        vote_link: str
        Link to the top.gg vote page.
    vote_reward_info_channel: int
        The Channel where vote reward infos are sent.
    vote_hook_channel: int
        The channel where you send your vote notifications.
    fusion_levels: int
        How many fusion levels there are.
    fusion_ball_need: list[int]
        how many cards you need to fuse
    fusion_result_event: list[int]
        The event ID which the result card should have.
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

    # vote
    vote_link: str = "https://top.gg/bot/1073275888466145370"
    vote_reward_info_channel: int = 1126956245891432599
    vote_hook_channel: int = 1124417376809656330

    collectible_name: str = "countryball"
    bot_name: str = "BallsDex"
    players_group_cog_name: str = "balls"

    # /fusion
    fusion_levels: int = 0
    fusion_ball_need: list[int] = field(default_factory=list)
    fusion_result_event: list[int] = field(default_factory=list)

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
    settings.prefix = content["text-prefix"]
    settings.team_owners = content.get("owners", {}).get("team-members-are-owners", False)
    settings.co_owners = content.get("owners", {}).get("co-owners", [])
        
    settings.vote_link = content["voting"]["vote-link"]
    settings.vote_reward_info_channel = content["voting"]["vote-reward-info-channel"]
    settings.vote_hook_channel = content["voting"]["vote-hook-channel"]

    settings.fusion_levels = len(content["fusion"]["fusion-ball-need"] or [])
    settings.fusion_ball_need = content["fusion"]["fusion-ball-need"] or []
    settings.fusion_result_event = content["fusion"]["fusion-result-event"] or []
    
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

    settings.log_channel = content.get("log-channel", None)

    settings.prometheus_enabled = content["prometheus"]["enabled"]
    settings.prometheus_host = content["prometheus"]["host"]
    settings.prometheus_port = content["prometheus"]["port"]
    log.info("Settings loaded.")


def write_default_settings(path: "Path"):
    path.write_text(
        """# yaml-language-server: $schema=json-config-ref.json

# paste the bot token after regenerating it here
discord-token: 

# prefix for old-style text commands, mostly unused
text-prefix: r.

# settings for voting
voting:

  # link to the top.gg vote page
  vote-link: https://top.gg/bot/1073275888466145370

  # The Channel where infos users will be informed about theyr vote-rewards.
  vote-reward-info-channel: 1126956245891432599

  # the channel where your vote webhook sends vote notifications.
  vote-hook-channel: 1124417376809656330

    
# define the recurces need for fusing
fusion:

  # How many balls you need to fuse (in level order)
  fusion-ball-need: 

  # The ID if the event the result card got (in leveld order).
  fusion-result-event: 


# define the elements given with the /about command
about:

  # define the beginning of the description of /about
  # the other parts is automatically generated
  description: >
    Collect countryballs on Discord, exchange them and battle with friends!

  # override this if you have a fork
  github-link: https://github.com/GamingadlerHD/WorldDex

  # valid invite for a Discord server
  discord-invite: https://discord.gg/CHv5TZNwKd  # BallsDex official server

  terms-of-service: https://gist.github.com/GamingadlerHD/ab167753d4a479fbf0535750891d4412
  privacy-policy: https://gist.github.com/GamingadlerHD/31d6601feef544b3f3a35560b42e5496

# WORK IN PROGRESS, DOES NOT FULLY WORK
# override the name "countryballs" in the bot
collectible-name: nation

# WORK IN PROGRESS, DOES NOT FULLY WORK
# override the name "BallsDex" in the bot
bot-name: NationDex

# players group cog command name
# this is /balls by default, but you can change it for /animals or /rocks for example
players-group-cog-name: nations

# enables the /admin command
admin-command:

  # all items here are list of IDs. example on how to write IDs in a list:
  # guild-ids:
  #   - 1049118743101452329
  #   - 1078701108500897923

  # list of guild IDs where /admin should be registered
  guild-ids:
      - 1108817636105666600
      - 659025574940901407

  # list of role IDs having full access to /admin
  root-role-ids:
      - 1109158375964553230
      - 659028509041229825

  # list of role IDs having partial access to /admin
  admin-role-ids:
      - 1109158605443305503
      - 659028509041229825

# log channel for moderation actions
log-channel: 1108817637896618048

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
