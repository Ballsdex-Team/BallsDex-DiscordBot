from django.contrib import admin


class BallsdexAdminSite(admin.AdminSite):
    site_header = "Ballsdex administration"  # TODO: use configured bot name
    site_title = "Ballsdex admin panel"
    site_url = None  # type: ignore
    final_catch_all_view = False
