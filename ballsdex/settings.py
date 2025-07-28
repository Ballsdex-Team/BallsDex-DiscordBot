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
    plural_collectible_name: str
        Usually "countryballs", can be replaced when possible
    bot_name: str
        Usually "BallsDex", can be replaced when possible
    players_group_cog_name: str
        Set the name of the base command of the "players" cog, /balls by default
    favorited_collectible_emoji: str
        Set the emoji used to represent a favorited countryball, "❤️" by default.
    max_favorites: int
        Set the maximum amount of favorited countryballs a user can have, 50 by default.
    max_attack_bonus:
        Set the biggest/smallest attack bonus that a spawned countryball can have.
    max_health_bonus:
        Set the biggest/smallest health bonus that a spawned countryball can have.
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
    packages: list[str]
        List of packages the bot will load upon startup
    spawn_manager: str
        Python path to a class implementing `BaseSpawnManager`, handling cooldowns and anti-cheat
    webhook_url: str | None
        URL of a Discord webhook for admin notifications
    client_id: str
        ID of the Discord application
    client_secret: str
        Secret key of the Discord application (not the bot token)
    """

    bot_token: str = ""
    gateway_url: str | None = None
    shard_count: int | None = None
    prefix: str = "b."

    collectible_name: str = "countryball"
    plural_collectible_name: str = "countryballs"
    bot_name: str = "BallsDex"
    players_group_cog_name: str = "balls"
    favorited_collectible_emoji: str = "❤️"

    max_favorites: int = 50
    max_attack_bonus: int = 20
    max_health_bonus: int = 20
    show_rarity: bool = False

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

    packages: list[str] = field(default_factory=list)

    # metrics and prometheus
    prometheus_enabled: bool = False
    prometheus_host: str = "0.0.0.0"
    prometheus_port: int = 15260

    spawn_manager: str = "ballsdex.packages.countryballs.spawn.SpawnManager"

    # django admin panel
    webhook_url: str | None = None
    admin_url: str | None = None
    client_id: str = ""
    client_secret: str = ""

    # sentry details
    sentry_dsn: str = ""
    sentry_environment: str = "production"

    caught_messages: list[str] = field(default_factory=list)
    wrong_messages: list[str] = field(default_factory=list)
    spawn_messages: list[str] = field(default_factory=list)
    slow_messages: list[str] = field(default_factory=list)


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
    settings.plural_collectible_name = content.get(
        "plural-collectible-name", content["collectible-name"] + "s"
    )
    settings.bot_name = content["bot-name"]
    settings.players_group_cog_name = content["players-group-cog-name"]
    settings.favorited_collectible_emoji = content.get("favorited-collectible-emoji", "❤️")
    settings.show_rarity = content.get("show-rarity", False)

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
    settings.max_attack_bonus = content.get("max-attack-bonus", 20)
    settings.max_health_bonus = content.get("max-health-bonus", 20)

    settings.packages = content.get("packages") or [
        "ballsdex.packages.admin",
        "ballsdex.packages.balls",
        "ballsdex.packages.config",
        "ballsdex.packages.countryballs",
        "ballsdex.packages.info",
        "ballsdex.packages.players",
        "ballsdex.packages.trade",
    ]

    settings.spawn_manager = content.get(
        "spawn-manager", "ballsdex.packages.countryballs.spawn.SpawnManager"
    )

    if admin := content.get("admin-panel"):
        settings.webhook_url = admin.get("webhook-url")
        settings.client_id = admin.get("client-id")
        settings.client_secret = admin.get("client-secret")
        settings.admin_url = admin.get("url")

    if sentry := content.get("sentry"):
        settings.sentry_dsn = sentry.get("dsn")
        settings.sentry_environment = sentry.get("environment")

    if catch := content.get("catch"):
        settings.spawn_messages = catch.get("spawn_msgs") or ["A wild {collectible} appeared!"]
        settings.caught_messages = catch.get("caught_msgs") or ["{user} You caught **{ball}**!"]
        settings.wrong_messages = catch.get("wrong_msgs") or ["{user} Wrong name!"]
        settings.slow_messages = catch.get("slow_msgs") or [
            "{user} Sorry, this {collectible} was caught already!"
        ]

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
  discord-invite: https://discord.gg/INVITE_CODE

  terms-of-service: https://gist.github.com/ # replace with your own link
  privacy-policy: https://gist.github.com/ # replace with your own link

# WORK IN PROGRESS, DOES NOT FULLY WORK
# override the name "countryball" in the bot
collectible-name: countryball

# WORK IN PROGRESS, DOES NOT FULLY WORK
# override the name "countryballs" in the bot
plural-collectible-name: countryballs

# WORK IN PROGRESS, DOES NOT FULLY WORK
# override the name "BallsDex" in the bot
bot-name: BallsDex

# players group cog command name
# this is /balls by default, but you can change it for /animals or /rocks for example
players-group-cog-name: balls

# emoji used to represent a favorited collectible
favorited-collectible-emoji: ❤️

# maximum amount of favorites that are allowed
max-favorites: 50

# the highest/lowest possible attack bonus, do not leave empty
# this cannot be smaller than 0, enter a positive number
max-attack-bonus: 20

# the highest/lowest possible health bonus, do not leave empty
# this cannot be smaller than 0, enter a positive number
max-health-bonus: 20

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


# Admin panel related settings
admin-panel:

    # to enable Discord OAuth2 login, fill this
    # client ID of the Discord application (not the bot's user ID)
    client-id: 
    # client secret of the Discord application (this is not the bot token)
    client-secret: 

    # to get admin notifications from the admin panel, create a Discord webhook and paste the url
    webhook-url: 

    # this will provide some hyperlinks to the admin panel when using /admin commands
    # set to an empty string to disable those links entirely
    url: http://localhost:8000

# list of packages that will be loaded
packages:
  - ballsdex.packages.admin
  - ballsdex.packages.balls
  - ballsdex.packages.config
  - ballsdex.packages.countryballs
  - ballsdex.packages.info
  - ballsdex.packages.players
  - ballsdex.packages.trade

# prometheus metrics collection, leave disabled if you don't know what this is
prometheus:
  enabled: false
  host: "0.0.0.0"
  port: 15260

spawn-manager: ballsdex.packages.countryballs.spawn.SpawnManager

# sentry details, leave empty if you don't know what this is
# https://sentry.io/ for error tracking
sentry:
    dsn: ""
    environment: "production"

catch:
  # Add any number of messages to each of these categories. The bot will select a random
  # one each time.
  # {user} is mention. {collectible} is collectible name. {ball} is ball name, and 
  # {collectibles} is collectible plural.

  # the message that appears when a user catches a ball 
  caught_msgs:
    - "{user} You caught **{ball}**!"

  # the message that appears when a user gets the name wrong
  # here and only here, you can use {wrong} to show the wrong name that was entered
  # note that a user can put whatever they want into that field, so be careful
  wrong_msgs:
    # - {user} Wrong name! You put: {wrong}
    - "{user} Wrong name!"

  # the message that appears above the spawn art
  # {user} is not available here, because who would it ping?
  spawn_msgs:
    - "A wild {collectible} appeared!"

  # the message that appears when a user is to slow to catch a ball
  slow_msgs:
    - "{user} Sorry, this {collectible} was caught already!"
  """  # noqa: W291
    )


def update_settings(path: "Path"):
    content = path.read_text()

    add_owners = True
    add_config_ref = "# yaml-language-server: $schema=json-config-ref.json" not in content
    add_max_favorites = "max-favorites:" not in content
    add_max_attack = "max-attack-bonus" not in content
    add_max_health = "max-health-bonus" not in content
    add_plural_collectible = "plural-collectible-name" not in content
    add_packages = "packages:" not in content
    add_spawn_manager = "spawn-manager" not in content
    add_django = "Admin panel related settings" not in content
    add_sentry = "sentry:" not in content
    add_catch_messages = "catch:" not in content

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

    if add_max_favorites:
        content += """
# maximum amount of favorites that are allowed
max-favorites: 50
"""

    if add_max_attack:
        content += """
# the highest/lowest possible attack bonus, do not leave empty
# this cannot be smaller than 0, enter a positive number
max-attack-bonus: 20
"""

    if add_max_health:
        content += """
# the highest/lowest possible health bonus, do not leave empty
# this cannot be smaller than 0, enter a positive number
max-health-bonus: 20
"""
    if add_plural_collectible:
        content += """
# WORK IN PROGRESS, DOES NOT FULLY WORK
# override the name "countryballs" in the bot
plural-collectible-name: countryballs
"""

    if add_packages:
        content += """
# list of packages that will be loaded
packages:
  - ballsdex.packages.admin
  - ballsdex.packages.balls
  - ballsdex.packages.config
  - ballsdex.packages.countryballs
  - ballsdex.packages.info
  - ballsdex.packages.players
  - ballsdex.packages.trade
"""

    if add_spawn_manager:
        content += """
# define a custom spawn manager implementation
spawn-manager: ballsdex.packages.countryballs.spawn.SpawnManager
"""

    if add_django:
        content += """
# Admin panel related settings
admin-panel:

    # to enable Discord OAuth2 login, fill this
    # client ID of the Discord application (not the bot's user ID)
    client-id:
    # client secret of the Discord application (this is not the bot token)
    client-secret:

    # to get admin notifications from the admin panel, create a Discord webhook and paste the url
    webhook-url:

    # this will provide some hyperlinks to the admin panel when using /admin commands
    # set to an empty string to disable those links entirely
    url: http://localhost:8000

"""

    if add_sentry:
        content += """
# sentry details, leave empty if you don't know what this is
# https://sentry.io/ for error tracking
sentry:
    dsn: ""
    environment: "production"
"""

    if add_catch_messages:
        content += """
catch:
  # Add any number of messages to each of these categories. The bot will select a random
  # one each time.
  # {user} is mention. {collectible} is collectible name. {ball} is ball name, and
  # {collectibles} is collectible plural.

  # the message that appears when a user catches a ball
  caught_msgs:
    - "{user} You caught **{ball}**!"

  # the message that appears when a user gets the name wrong
  # here and only here, you can use {wrong} to show the wrong name that was entered
  # note that a user can put whatever they want into that field, so be careful
  wrong_msgs:
    # - {user} Wrong name! You put: {wrong}
    - "{user} Wrong name!"

  # the message that appears above the spawn art
  # {user} is not available here, because who would it ping?
  spawn_msgs:
    - "A wild {collectible} appeared!"

  # the message that appears when a user is to slow to catch a ball
  slow_msgs:
    - "{user} Sorry, this {collectible} was caught already!"
"""

    if any(
        (
            add_owners,
            add_config_ref,
            add_max_favorites,
            add_max_attack,
            add_max_health,
            add_plural_collectible,
            add_packages,
            add_spawn_manager,
            add_django,
            add_sentry,
            add_catch_messages,
        )
    ):
        path.write_text(content)
