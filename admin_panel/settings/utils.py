from typing import TYPE_CHECKING

from .models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


def format_currency(amount: int, shortened: bool = True, bot: "BallsDexBot | None" = None):
    if shortened:
        if settings.currency_symbol_before:
            return f"{settings.currency_symbol}{amount}"
        else:
            return f"{amount}{settings.currency_symbol}"
    else:
        if amount == 0:
            return f"no {settings.currency_display_name(bot)}"
        elif amount == 1:
            return f"{amount} {settings.currency_display_name(bot)}"
        else:
            return f"{amount} {settings.currency_display_plural(bot)}"
