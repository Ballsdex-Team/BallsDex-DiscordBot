from django.contrib.admin.apps import AdminConfig


class BallsdexAdminConfig(AdminConfig):
    default_site = "admin_panel.admin.BallsdexAdminSite"
