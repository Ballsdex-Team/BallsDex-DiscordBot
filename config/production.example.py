# Copy this file as "production.py" and set the environment variable
# DJANGO_SETTINGS_MODULE=admin_panel.settings.production to enable serving over the internet

from admin_panel.settings.production_base import *  # noqa: F403

# Generate a long random string here for your secret key. It is important to keep it secret,
# leaking it could allow attackers to do privilege escalation.
# A good way to generate a long key is to run "pwgen 64 1" on Linux
SECRET_KEY = None

ALLOWED_HOSTS = [
    "localhost"
    # place the domain of your website here
    # "ballsdex.com"
]

# Enable connection pooling, allowing multiple concurrent connections to be made to the database and divide the load
# Uncomment this with an appropriate number if you have a large bot
# DATABASES["default"].setdefault("OPTIONS", {})["pool"] = {"max_size": 20}
# If you wonder how many pools you need, check this:
# https://www.psycopg.org/psycopg3/docs/advanced/pool.html#what-s-the-right-size-for-the-pool
# The following eval will show you the result of get_stats():
# b.eval from django.db import connection
# from asgiref.sync import sync_to_async
# return await sync_to_async(lambda: connection.pool.get_stats())()


# If you are handling TLS/HTTPS yourself, uncomment this line to enforce HTTPS connections
# Do not uncomment if HTTPS is not handled locally (like Cloudflare), this will result in
# infinite redirections
#
# SECURE_SSL_REDIRECT = True


# You can read more about Django's security options by running "python3 manage.py check --deploy"
# or here: https://docs.djangoproject.com/en/5.1/ref/middleware/#module-django.middleware.security
