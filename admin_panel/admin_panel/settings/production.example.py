# Copy this file as "production.py" and set the environment variable
# DJANGO_SETTINGS_MODULE=admin_panel.settings.production to enable serving over the internet

from .production_base import *

# Generate a long random string here for your secret key. It is important to keep it secret,
# leaking it could allow attackers to do privilege escalation.
# A good way to generate a long key is to run "pwgen 64 1" on Linux
SECRET_KEY = None

ALLOWED_HOSTS = [
    "localhost",
    # place the domain of your website here
    # "ballsdex.com"
]
