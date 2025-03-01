from typing import TYPE_CHECKING, Literal

from ballsdex.packages.countryballs.spawn import BaseSpawnManager

if TYPE_CHECKING:
    import discord

    from ballsdex.core.bot import BallsDexBot

# It is a good idea to call importlib.reload on your custom module to make "b.reload countryballs"
# also reload the spawn manager. Otherwise, you'll be forced to fully restart to apply changes
#
# import importlib
# import yourpackage
# importlib.reload(yourpackage)
# ...
# manager_class_b = yourpackage.SpawnManager


class ABSpawner(BaseSpawnManager):
    """
    This is an unused class made available for A/B testing your spawn algorithms.
    https://en.wikipedia.org/wiki/A/B_testing

    Using this, you can mix two different spawn managers with a repartition of your choosing to
    test and see how well it performs. Prometheus can then be used to compare the results.

    Each guild will be assigned to one of your spawn manager defined below, using the configured
    percentage.
    """

    # chance of using algorithm a instead of b
    # if percentage=20, then algorithm a will be used on 20% of servers, and algorithm b on 80%
    percentage = 50

    # define your classes here
    manager_class_a: type[BaseSpawnManager]  # = SpawnManager
    manager_class_b: type[BaseSpawnManager]  # = YourCustomManager

    def __init__(self, bot: "BallsDexBot"):
        self.manager_a = self.manager_class_a(bot)
        self.manager_b = self.manager_class_b(bot)

    def get_manager(self, guild: "discord.Guild") -> BaseSpawnManager:
        """
        Return manager A or B for the guild. This will consistently return the same
        manager accross restarts, unless the percentage is changed.
        """
        # For fast and accurate repartition of guilds, random is not used, instead we rely on
        # their ID modulo 100 and see where it lands.
        # In a Discord ID, bits 22 to 64 correspond to the timestamp, so we shift the ID 22 bits
        # to the right and use the least significant bits (miliseconds) for our operation.
        # Without bit-shifting, the least significant bits wouldn't have a proper distribution
        # https://discord.com/developers/docs/reference#snowflakes
        if (guild.id >> 22) % 100 < self.percentage:
            return self.manager_a
        else:
            return self.manager_b

    async def handle_message(self, message: "discord.Message") -> bool | tuple[Literal[True], str]:
        assert message.guild
        manager = self.get_manager(message.guild)
        result = await manager.handle_message(message)
        if result is False:
            return False
        if isinstance(result, tuple):
            result, msg = result
            msg += f"-{manager.__class__.__name__}"
        else:
            msg = manager.__class__.__name__
        return result, msg

    async def admin_explain(
        self, interaction: "discord.Interaction[BallsDexBot]", guild: "discord.Guild"
    ):
        manager = self.get_manager(guild)
        await manager.admin_explain(interaction, guild)
        if manager == self.manager_a:
            a_or_b = "A"
            percentage = self.percentage
        else:
            a_or_b = "B"
            percentage = 100 - self.percentage
        await interaction.followup.send(
            f"[AB Spawner] Server {guild.name} ({guild.id}) has been assigned to spawn manager "
            f"{a_or_b} (`{manager.__class__.__name__}`) ({percentage}% chance)",
            ephemeral=True,
        )
