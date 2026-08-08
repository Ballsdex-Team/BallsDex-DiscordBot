import hashlib
import hmac
import json
import logging
import random
import re
import time
from datetime import timedelta
from io import BytesIO

import aiohttp
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from ballsdex.core.image_generator.image_gen import draw_card
from bd_models.models import Ball, BallInstance, Player, Special, VoteInteraction, VoteRecord
from preview.utils import refresh_cache

from .models import Settings

log = logging.getLogger("ballsdex.webhook.topgg")

# Discord interaction tokens are only valid for 15 minutes after the original interaction
INTERACTION_TOKEN_LIFETIME = timedelta(minutes=15)

# https://docs.top.gg/webhooks/overview - current (v1) signature scheme: header value looks like
# "t=<unix seconds>,v1=<hex hmac-sha256 of '{timestamp}.{raw body}'>"
TOPGG_SIGNATURE_RE = re.compile(r"^t=(?P<timestamp>\d+),v1=(?P<signature>[0-9a-f]{64})$")
SIGNATURE_TOLERANCE_SECONDS = 300


async def _get_random_active_special() -> Special | None:
    now = timezone.now()
    population = [
        x
        async for x in Special.objects.filter(hidden=False).filter(
            Q(start_date__isnull=True) | Q(start_date__lte=now), Q(end_date__isnull=True) | Q(end_date__gte=now)
        )
    ]
    if not population:
        return None
    return random.choices(population=population, weights=[x.rarity for x in population], k=1)[0]


async def _send_ephemeral_reward(discord_id: int, instance: BallInstance) -> None:
    """
    Sends the vote reward as an ephemeral follow-up to the player's most recent /vote command,
    visible only to them. Silently does nothing if they never ran /vote, or ran it more than
    15 minutes ago (the reward is still granted either way, just not announced).
    """
    pending = await VoteInteraction.objects.filter(discord_id=discord_id).afirst()
    if pending is None:
        return

    try:
        if timezone.now() - pending.created_at > INTERACTION_TOKEN_LIFETIME:
            return

        ball = instance.ball
        special = instance.special
        reward_name = f"{special.name} {ball.country}" if special else ball.country
        content = f"🎉 Thanks for voting! Here's your reward: **{reward_name}**"

        await refresh_cache()
        image, save_kwargs = draw_card(instance)
        buffer = BytesIO()
        image.save(buffer, **save_kwargs)
        buffer.seek(0)

        form = aiohttp.FormData()
        form.add_field(
            "payload_json", json.dumps({"content": content, "flags": 64}), content_type="application/json"
        )
        form.add_field("files[0]", buffer, filename="card.webp", content_type="image/webp")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://discord.com/api/v10/webhooks/{pending.application_id}/{pending.token}",
                data=form,
            ) as resp:
                if resp.status >= 400:
                    log.warning(
                        "Failed to send ephemeral vote reward: HTTP %s - %s", resp.status, await resp.text()
                    )
    except Exception:
        log.exception("Failed to send ephemeral vote reward for player %s", discord_id)
    finally:
        await pending.adelete()


@csrf_exempt
async def topgg_webhook(request: HttpRequest) -> JsonResponse:
    """
    Receives Top.gg's "someone voted" webhook (v1 signature scheme) and grants a random reward
    to the voter.

    Configure this URL (<your admin panel base URL>/webhook/topgg) and a secret on your bot's
    Top.gg "Webhooks" page, then paste the same secret in Settings.vote_webhook_secret.
    Using the webhook (instead of trusting the /vote command itself) is what guarantees the
    reward is only granted for a real vote, not just for running the command.
    """
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    settings = await Settings.objects.afirst()
    if settings is None or not settings.vote_webhook_secret:
        return JsonResponse({"detail": "Vote webhook is not configured"}, status=503)

    match = TOPGG_SIGNATURE_RE.match(request.headers.get("x-topgg-signature", ""))
    if match is None:
        return JsonResponse({"detail": "Unauthorized"}, status=401)

    timestamp, signature = match.group("timestamp"), match.group("signature")
    if abs(time.time() - int(timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
        return JsonResponse({"detail": "Unauthorized"}, status=401)

    signed_payload = f"{timestamp}.{request.body.decode()}".encode()
    expected_signature = hmac.new(settings.vote_webhook_secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return JsonResponse({"detail": "Unauthorized"}, status=401)

    try:
        payload = json.loads(request.body)
        event_type = payload["type"]
        discord_id = int(payload["data"]["user"]["platform_id"])
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return JsonResponse({"detail": "Invalid payload"}, status=400)

    if event_type != "vote.create":
        # Top.gg sends {"type": "webhook.test"} when testing the webhook from its dashboard, no reward for those
        return JsonResponse({"detail": "Test ping received"}, status=200)

    player, _ = await Player.objects.aget_or_create(discord_id=discord_id)

    last_vote = await VoteRecord.objects.filter(player=player).order_by("-voted_at").afirst()
    if last_vote is not None and timezone.now() - last_vote.voted_at < timedelta(hours=12):
        log.info("Duplicate vote webhook for player %s ignored (already rewarded within 12h)", discord_id)
        return JsonResponse({"detail": "Already rewarded for this vote window"}, status=200)

    balls = [
        x
        async for x in Ball.objects.filter(
            enabled=True, tradeable=True, rarity__range=(settings.vote_min_rarity, settings.vote_max_rarity)
        )
    ]
    reward = None
    if balls:
        ball = random.choices(population=balls, weights=[x.rarity for x in balls], k=1)[0]
        special = None
        if random.random() < settings.vote_special_chance:
            special = await _get_random_active_special()
        reward = await BallInstance.objects.acreate(
            player=player,
            ball=ball,
            special=special,
            health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
            attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
        )
        await _send_ephemeral_reward(discord_id, reward)
    else:
        log.warning("No ball available in the configured vote rarity range, no reward granted for %s", discord_id)

    await VoteRecord.objects.acreate(player=player, reward=reward)

    return JsonResponse({"detail": "Vote recorded"}, status=200)
