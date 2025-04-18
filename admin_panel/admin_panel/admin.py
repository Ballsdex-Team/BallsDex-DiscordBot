from django.contrib import admin

from ballsdex.settings import settings


class BallsdexAdminSite(admin.AdminSite):
    site_header = f"{settings.bot_name.title()} administration"
    site_title = f"{settings.bot_name.title()} admin panel"
    site_url = None  # type: ignore
    final_catch_all_view = False
