from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


class SecurityHeadersMiddleware:
    def __init__(self, get_response: Callable[["HttpRequest"], "HttpResponse"]):
        self.get_response = get_response

    def __call__(self, request: "HttpRequest") -> "HttpResponse":
        response = self.get_response(request)
        response["Content-Security-Policy"] = (
            "default-src 'self' http://*.discordapp.com http://discord.com; frame-ancestors 'self'"
        )
        response["X-XSS-Protection"] = "1; mode=block"
        response["X-Robots-Tag"] = "none"
        response["Referrer-Policy"] = "same-origin"
        return response
