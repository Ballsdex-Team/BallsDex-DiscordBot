from typing import TYPE_CHECKING

from .models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


def format_currency(amount: int, shortened: bool = True, bot: "BallsDexBot | None" = None):
    if shortened:
        # the emoji takes priority over the symbol, but it can only be resolved with the bot
        emoji = settings.currency_emoji(bot) if bot is not None else None
        if emoji:
            if settings.currency_symbol_before:
                return f"{emoji} {amount}"
            else:
                return f"{amount} {emoji}"
        if settings.currency_symbol:
            if settings.currency_symbol_before:
                return f"{settings.currency_symbol}{amount}"
            else:
                return f"{amount}{settings.currency_symbol}"
        # neither an emoji nor a symbol is configured, fall back to the full form
    if amount == 0:
        return f"no {settings.currency_display_name(bot)}"
    elif amount == 1:
        return f"{amount} {settings.currency_display_name(bot)}"
    else:
        return f"{amount} {settings.currency_display_plural(bot)}"
