# ruff: noqa: F401
import warnings

from settings.models import settings

warnings.deprecated(
    'Importing settings from this location is deprecated, use "from settings.models import settings" instead'
)
