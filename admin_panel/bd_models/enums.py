from django.db import models


class DonationPolicy(models.IntegerChoices):
    ALWAYS_ACCEPT = 1
    REQUEST_APPROVAL = 2
    ALWAYS_DENY = 3
    FRIENDS_ONLY = 4


class PrivacyPolicy(models.IntegerChoices):
    ALLOW = 1
    DENY = 2
    SAME_SERVER = 3
    FRIENDS = 4


class MentionPolicy(models.IntegerChoices):
    ALLOW = 1
    DENY = 2


class FriendPolicy(models.IntegerChoices):
    ALLOW = 1
    DENY = 2


class TradeCooldownPolicy(models.IntegerChoices):
    COOLDOWN = 1
    BYPASS = 2
