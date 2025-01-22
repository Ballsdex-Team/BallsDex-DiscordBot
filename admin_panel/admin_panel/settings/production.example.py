# Copy this file as "production.py" and set the environment variable
# DJANGO_SETTINGS_MODULE="admin_panel.settings.production" to enable serving over the internet

from .base import *

DEBUG = False

# Force python-social-auth (Discord OAuth2) to use https redirection
SOCIAL_AUTH_REDIRECT_IS_HTTPS = True

# Correctly read the headers when using a proxy like nginx
# Failing to configure this setting will result in CSRF errors in HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Generate a long random string here for your secret key. It is important to keep it secret,
# leaking it could allow attackers to do privilege escalation.
# A good way to generate a long key is to run "pwgen 64 1" on Linux
SECRET_KEY = None

ALLOWED_HOSTS = [
    "localhost",
    # place the domain of your website here
    # "ballsdex.com"
]
