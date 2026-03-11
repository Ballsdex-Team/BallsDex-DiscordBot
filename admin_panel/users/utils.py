from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .models import User

    get_user_model: Callable[[], type[User]]
else:
    from django.contrib.auth import get_user_model  # noqa: F401
