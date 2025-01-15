from .base import *

SECRET_KEY = "insecure"
MIDDLEWARE.append("admin_panel.middleware.LocalIPOnlyMiddleware")
