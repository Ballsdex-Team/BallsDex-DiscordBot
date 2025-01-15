import re
from typing import Callable

from django.http import HttpRequest, HttpResponse

LOCAL_IP_RE = re.compile(r"(192\.168)|(127\.[0-9]{0,3})\.[0-9]{0,3}\.[0-9]{0,3}")


def get_client_ip(request: "HttpRequest") -> str | None:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[-1].strip()
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


class LocalIPOnlyMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        ip = get_client_ip(request)
        if not ip:
            return self.get_response(request)
        if ip == "0.0.0.0":
            return self.get_response(request)
        if LOCAL_IP_RE.match(ip):
            return self.get_response(request)
        return HttpResponse(
            "The Ballsdex admin panel is configured for local-only traffic, "
            f"but you have an external IP ({ip}).\n"
            "If you want to serve the admin panel to the internet, please read the documentation "
            "on how to create the production.py file.",
            status=401,
        )
