from django.contrib import admin

from ..models import GuildConfig


@admin.register(GuildConfig)
class GuildAdmin(admin.ModelAdmin):
    list_display = ("guild_id", "spawn_channel", "enabled", "silent")
    list_filter = ("enabled", "silent")

    search_fields = ("guild_id", "spawn_channel")
    search_help_text = "Search by guild ID or spawn channel ID"
