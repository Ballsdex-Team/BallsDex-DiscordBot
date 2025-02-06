class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'self'"
        response["X-XSS-Protection"] = "1; mode=block"
        response["X-Robots-Tag"] = "none"
        response["Referrer-Policy"] = "same-origin"
        return response
