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
    prefix: str
        Prefix for text commands, mostly unused. Defaults to "b."
    admin_guild_ids: list[int]
        List of guilds where the /admin command must be registered
    root_role_ids: list[int]
        List of roles that have full access to the /admin command
    admin_role_ids: list[int]
        List of roles that have partial access to the /admin command (only blacklist and guilds)
    """

    bot_token: str = ""
    prefix: str = "b."
    admin_guild_ids: list[int] = field(default_factory=list)
    root_role_ids: list[int] = field(default_factory=list)
    admin_role_ids: list[int] = field(default_factory=list)
    prometheus_enabled: bool = False
    prometheus_host: str = "0.0.0.0"
    prometheus_port: int = 15260


settings = Settings()


def read_settings(path: "Path"):
    content = yaml.load(path.read_text(), yaml.Loader)
    settings.bot_token = content["discord-token"]
    settings.prefix = content["text-prefix"]
    settings.admin_guild_ids = content["admin-command"]["guild-ids"] or []
    settings.root_role_ids = content["admin-command"]["root-role-ids"] or []
    settings.admin_guild_ids = content["admin-command"]["admin-role-ids"] or []
    settings.prometheus_enabled = content["prometheus"]["enabled"]
    settings.prometheus_host = content["prometheus"]["host"]
    settings.prometheus_port = content["prometheus"]["port"]
    log.info("Settings loaded.")
