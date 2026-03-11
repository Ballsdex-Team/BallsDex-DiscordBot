from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.db.models import OuterRef, Subquery
from django.db.models.functions import Cast, Coalesce


class CustomUserManager(UserManager):
    def get_queryset(self) -> models.QuerySet[User]:
        return (
            super()
            .get_queryset()
            .annotate(
                discord_id=Coalesce(
                    Cast(
                        Subquery(
                            super()
                            .get_queryset()
                            .filter(social_auth__user_id=OuterRef("pk"), social_auth__provider="discord")
                            .values("social_auth__uid")[:1]
                        ),
                        output_field=models.PositiveBigIntegerField(),
                    ),
                    models.F("discord_user_id"),
                    output_field=models.PositiveBigIntegerField(),
                )
            )
        )


class User(AbstractUser):
    discord_user_id = models.PositiveBigIntegerField(
        help_text="Fallback Discord user ID. Only use this if OAuth2 is disabled!", null=True, blank=True
    )
    objects = CustomUserManager()

    REQUIRED_FIELDS = ["discord_user_id"]

    if TYPE_CHECKING:
        discord_id: int | None
