from django.contrib import admin

from settings.models import settings


class BallsdexAdminSite(admin.AdminSite):
    site_url = None  # type: ignore
    final_catch_all_view = False

    # using properties allows reading settings after startup
    @property
    def site_header(self):
        return f"{settings.bot_name} administration"

    @property
    def site_title(self):
        return f"{settings.bot_name} admin panel"
