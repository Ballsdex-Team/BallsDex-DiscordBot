from settings.models import PromptMessage, Settings


def import_settings_from_yaml(content: dict, s: Settings) -> None:
    s.bot_token = content.get("discord-token") or s.bot_token
    s.prefix = content.get("text-prefix") or s.prefix
    owners: dict
    if owners := content.get("owners", {}):
        s.team_owners = owners.get("team-members-are-owners", False)
        s.coowners = ";".join(str(x) for x in owners.get("co-owners") or [])

    s.collectible_name = content.get("collectible-name") or s.collectible_name
    s.plural_collectible_name = content.get("plural-collectible-name") or s.plural_collectible_name
    s.bot_name = content.get("bot-name") or s.bot_name
    s.balls_slash_name = content.get("players-group-cog-name") or s.balls_slash_name
    s.favorited_collectible_emoji = content.get("favorited-collectible-emoji") or s.favorited_collectible_emoji
    s.max_favorites = content.get("max-favorites") or s.max_favorites
    s.max_attack_bonus = content.get("max-attack-bonus") or s.max_attack_bonus
    s.max_health_bonus = content.get("max-health-bonus") or s.max_health_bonus
    s.show_rarity = content.get("show-rarity", False)
    s.admin_channel_ids = (
        ";".join(str(x) for x in content.get("admin-command", {}).get("admin-channels-ids") or [])
        or s.admin_channel_ids
    )

    about: dict
    if about := content.get("about", {}):
        s.about_description = about.get("description") or s.about_description
        s.repository = about.get("github-link") or s.repository
        s.discord_invite = about.get("discord-invite") or s.discord_invite
        s.terms_of_service = about.get("terms-of-service") or s.terms_of_service
        s.privacy_policy = about.get("privacy-policy") or s.privacy_policy

    prometheus: dict
    if prometheus := content.get("prometheus", {}):
        s.prometheus_enabled = prometheus.get("enabled") or s.prometheus_enabled
        s.prometheus_host = prometheus.get("host") or s.prometheus_host
        s.prometheus_port = prometheus.get("port") or s.prometheus_port

    spawn_range: tuple[int, int]
    if spawn_range := content.get("spawn-chance-range", ()):
        s.spawn_chance_min = spawn_range[0]
        s.spawn_chance_max = spawn_range[1]

    admin_panel: dict
    if admin_panel := content.get("admin-panel", {}):
        s.client_id = admin_panel.get("client-id") or s.client_id
        s.client_secret = admin_panel.get("client-secret") or s.client_secret
        s.webhook_logging = admin_panel.get("webhook-url") or s.webhook_logging

    sentry: dict
    if sentry := content.get("sentry", {}):
        s.sentry_dsn = sentry.get("dsn") or s.sentry_dsn
        s.sentry_env = sentry.get("environment") or s.sentry_env

    catch: dict
    if catch := content.get("catch", {}):
        s.catch_button_label = catch.get("catch_button_label") or s.catch_button_label
        objects: list[PromptMessage] = []
        for msg in catch.get("spawn_msgs", []):
            objects.append(PromptMessage(category=PromptMessage.PromptType.SPAWN, message=msg, settings=s))
        for msg in catch.get("caught_msgs", []):
            objects.append(PromptMessage(category=PromptMessage.PromptType.CATCH, message=msg, settings=s))
        for msg in catch.get("wrong_msgs", []):
            objects.append(PromptMessage(category=PromptMessage.PromptType.WRONG, message=msg, settings=s))
        for msg in catch.get("slow_msgs", []):
            objects.append(PromptMessage(category=PromptMessage.PromptType.SLOW, message=msg, settings=s))
        PromptMessage.objects.bulk_create(objects, ignore_conflicts=True)

    s.save()
