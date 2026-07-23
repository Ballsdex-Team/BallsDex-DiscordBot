import logging

from discord import app_commands
from asgiref.sync import sync_to_async
from discord.ext import commands

from django.db import IntegrityError

from ballsdex.core.bot import BallsDexBot
from ballsdex.core.utils import checks
from ballsdex.core.utils.buttons import ConfirmChoiceView
from settings.models import load_settings, Settings, PromptMessage

from .flags import PromptMessageFlags, DeleteMessageFlags

log = logging.getLogger(__name__)

@commands.hybrid_group()
@checks.has_permissions("bd_models.view_player")
async def promptmessage(ctx: commands.Context[BallsDexBot]):
    """
    Prompt message commands
    """
    await ctx.send_help(ctx.command)


@promptmessage.command()
@app_commands.choices(
    type=[
        app_commands.Choice(name="Catch", value=1),
        app_commands.Choice(name="Wrong", value=2),
        app_commands.Choice(name="Spawn", value=3),
        app_commands.Choice(name="Slow", value=4),
    ]
)
async def create(
    ctx: commands.Context[BallsDexBot],
    type: int,
    message: str,
    *,
    flags: PromptMessageFlags,
):
    """
    Create a spawn message.

    Parameters
    ----------
    type: int
        The type of prompt message it should be. They are Catch, Wrong, Spawn, and Slow.
    message: str
        Contents of the message to be added. Supports the curly bracket substitutions.
    """
    if type > 4 or type < 1:
        await ctx.send("Invalid int value passed for the type of flag.", ephemeral=True)
        return
    await ctx.defer(ephemeral=True)

    try:
        vector = PromptMessage()
        vector.category = type
        vector.message = message
        vector.rarity = flags.rarity
        if vector.settings_id is None:
            vector.settings = await sync_to_async(Settings.objects.first)()
    except IntegrityError:
        log.exception(
            f"Failed creating a prompt message because "
            f"that exact prompt message in the same category already exists.",
            exc_info=True,
            extra={"webhook": True},
        )
        await ctx.send(
            f"An error occurred while creating the {settings.collectible_name}. Check the error in bot logs.",
            ephemeral=True,
        )
        return
    except Exception:
        log.exception(
            "Failed creating a prompt message with admin command", exc_info=True, extra={"webhook": True}
        )
        await ctx.send(
            "An error occurred while creating the prompt message. Check the error in bot logs.",
            ephemeral=True,
        )
        return
    else:
        await vector.asave()
        await sync_to_async(load_settings)()
        await ctx.send("A new prompt message has been created! The cache has been reloaded with the change.\n"
                       f"The message is: {vector.message}\n"
                       f"It is of category {vector.category} with rarity {vector.rarity}")
        log.info(f'{ctx.author} created a new prompt message "{vector.message}" in the category {vector.category} with rarity {vector.rarity}',
                 extra={"webhook": True})


@promptmessage.command()
async def delete(
    ctx: commands.Context[BallsDexBot],
    *,
    flags: DeleteMessageFlags,
):
    """
    Delete a spawn message.

    Parameters
    ----------
    """
    try:
        dog = 4
    except ValueError:
        await ctx.send(
            "The message you provided is not valid.",
            ephemeral=True,
        )
        return
    except Exception:
        await ctx.send(
            "An error occurred while deleting the prompt message. Check the error in bot logs.",
            ephemeral=True,
        )
        return

    view = ConfirmChoiceView(
        ctx, accept_message=f"Confirmed, deleting...", cancel_message="Request cancelled."
    )
    await ctx.send(
        f"You are about to delete {flags.message}. Are you sure?",
        view=view,
        ephemeral=True,
    )
    await view.wait()
    if not view.value:
        return

    await ball.adelete()
    await ctx.send(f"{flags.message} deleted.", ephemeral=True)
    log.info(f"{ctx.author} deleted {flags.message}).", extra={"webhook": True})