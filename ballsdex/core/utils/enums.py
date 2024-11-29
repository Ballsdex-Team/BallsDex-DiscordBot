import enum

DONATION_POLICY_MAP = {
    1: "Accept all donations",
    2: "Approve donations",
    3: "Deny all donations",
    4: "Accept donations from friends only",
}

PRIVATE_POLICY_MAP = {1: "Public", 2: "Private", 3: "Mutual Servers", 4: "Friends"}

MENTION_POLICY_MAP = {1: "Allow all mentions", 2: "Deny all mentions"}

FRIEND_POLICY_MAP = {1: "Allow all friend requests", 2: "Deny all friend requests"}


class SortingChoices(enum.Enum):
    alphabetic = "ball__country"
    catch_date = "-catch_date"
    rarity = "ball__rarity"
    special = "special__id"
    health = "health"
    attack = "attack"
    health_bonus = "-health_bonus"
    attack_bonus = "-attack_bonus"
    stats_bonus = "stats"
    total_stats = "total_stats"

    # manual sorts are not sorted by SQL queries but by our code
    # this may be do-able with SQL still, but I don't have much experience ngl
    duplicates = "manualsort-duplicates"
