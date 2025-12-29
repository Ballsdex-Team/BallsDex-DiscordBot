from .models import settings


def format_currency(amount: int, shortened: bool = True):
    if shortened:
        if settings.currency_symbol_before:
            return f"{settings.currency_symbol}{amount}"
        else:
            return f"{settings.currency_symbol}{amount}"
    else:
        if amount == 0:
            return f"no {settings.currency_name}"
        elif amount == 1:
            return f"{amount} {settings.currency_name}"
        else:
            return f"{amount} {settings.currency_plural}"
