from django.apps import apps
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin_urls = admin.site.get_urls()
admin_urls[1].default_args["extra_context"] = {  # type: ignore
    "pwlogin": "django.contrib.auth.backends.ModelBackend" in settings.AUTHENTICATION_BACKENDS
}

urlpatterns = (
    [
        path("/action-forms/", include("django_admin_action_forms.urls")),
        path("", (admin_urls, "admin", admin.site.name)),
        path("", include("preview.urls")),
        path("", include("social_django.urls", namespace="social")),
    ]
    + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
)

for app_config in apps.get_app_configs():
    prefix = getattr(app_config, "url_prefix", None)
    if prefix is not None:
        urlpatterns.append(path(prefix, include(f"{app_config.name}.urls")))

if "debug_toolbar" in settings.INSTALLED_APPS:
    try:
        from debug_toolbar.toolbar import debug_toolbar_urls
    except ImportError:
        pass
    else:
        urlpatterns.extend(debug_toolbar_urls())
