from django import template

register = template.Library()


@register.simple_tag
def has_enabled_discord_login():
    from settings.models import settings

    return bool(settings.client_id and settings.client_secret)
