from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = (
    [
        path("admin/", admin.site.urls),
        path("", include("preview.urls")),
        path("", include("social_django.urls", namespace="social")),
    ]
    + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
)

if settings.DEBUG:
    try:
        from debug_toolbar.toolbar import debug_toolbar_urls
    except ImportError:
        pass
    else:
        urlpatterns.extend(debug_toolbar_urls())
