from __future__ import annotations

import logging
import random
import re
import string
from datetime import date
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageOps, ImageSequence

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.frames")

FRAME_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")


def get_active_frame(capacity_logic: Any) -> dict | None:
    """Return today's frame entry from capacity_logic if one exists, else None."""
    if not isinstance(capacity_logic, dict):
        return None
    key = date.today().strftime("%m-%d-%Y")
    entry = capacity_logic.get(key)
    if isinstance(entry, dict):
        return entry
    return None


def _random_name() -> str:
    source = string.ascii_uppercase + string.ascii_lowercase + string.ascii_letters
    return "".join(random.choices(source, k=15))


class FramesCog(commands.Cog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self._originals: dict[str, Any] = {}
        self._patch()

    def cog_unload(self) -> None:
        import ballsdex.core.image_generator.image_gen as image_gen_module
        import bd_models.models as bd_models_module
        import ballsdex.core.utils.sorting as sorting_module
        from ballsdex.packages.countryballs.countryball import BallSpawnView
        from ballsdex.core.utils.menus.formatter import CountryballFormatter
        from ballsdex.core.utils.enums import FilteringChoices
        from bd_models.models import BallInstance

        if "spawn" in self._originals:
            BallSpawnView.spawn = self._originals["spawn"]  # type: ignore[method-assign]
        if "get_catch_message" in self._originals:
            BallSpawnView.get_catch_message = self._originals["get_catch_message"]  # type: ignore[method-assign]
        if "draw_card" in self._originals:
            image_gen_module.draw_card = self._originals["draw_card"]
            bd_models_module.draw_card = self._originals["draw_card"]
        if "format_page" in self._originals:
            CountryballFormatter.format_page = self._originals["format_page"]  # type: ignore[method-assign]
        if "filter_balls" in self._originals:
            sorting_module.filter_balls = self._originals["filter_balls"]
        if "balls_cog_filter_balls" in self._originals:
            try:
                import ballsdex.packages.balls.cog as balls_cog_module
                balls_cog_module.filter_balls = self._originals["balls_cog_filter_balls"]  # type: ignore[attr-defined]
            except Exception:
                pass
        if "ball_instance_save" in self._originals:
            BallInstance.save = self._originals["ball_instance_save"]  # type: ignore[method-assign]
        if "ball_instance_acreate" in self._originals:
            BallInstance.objects.acreate = self._originals["ball_instance_acreate"]  # type: ignore[assignment]

        # Remove the injected enum member
        if hasattr(FilteringChoices, "frame"):
            FilteringChoices._member_map_.pop("frame", None)  # type: ignore[attr-defined]
            FilteringChoices._value2member_map_.pop("frame", None)  # type: ignore[attr-defined]
            try:
                FilteringChoices._member_names_.remove("frame")  # type: ignore[attr-defined]
            except ValueError:
                pass
            try:
                type.__delattr__(FilteringChoices, "frame")
            except AttributeError:
                pass

        log.info("Frames patches removed.")

    def _patch(self) -> None:
        import ballsdex.core.image_generator.image_gen as image_gen_module
        import bd_models.models as bd_models_module
        from django.core.exceptions import ObjectDoesNotExist
        from ballsdex.packages.countryballs.countryball import BallSpawnView
        from ballsdex.core.utils.menus.formatter import CountryballFormatter
        from settings.models import PromptMessage, settings
        from bd_models.models import BallInstance

        # ── BallInstance.save ──────────────────────────────────────────────────

        original_ball_instance_save = BallInstance.save

        def patched_ball_instance_save(self, *args, **kwargs):
            if not self.pk and not self.extra_data:
                try:
                    key = date.today().strftime("%m-%d-%Y")
                    entry = self.ball.capacity_logic.get(key)
                    if isinstance(entry, dict):
                        self.extra_data = entry
                except Exception:
                    pass
            return original_ball_instance_save(self, *args, **kwargs)

        self._originals["ball_instance_save"] = BallInstance.save
        BallInstance.save = patched_ball_instance_save  # type: ignore[method-assign]

        # ── BallInstance.objects.acreate ───────────────────────────────────────

        original_acreate = BallInstance.objects.acreate

        async def patched_acreate(**kwargs):
            if "extra_data" not in kwargs:
                ball = kwargs.get("ball")
                if ball is not None:
                    try:
                        key = date.today().strftime("%m-%d-%Y")
                        entry = ball.capacity_logic.get(key)
                        if isinstance(entry, dict):
                            kwargs["extra_data"] = entry
                    except Exception:
                        pass
            return await original_acreate(**kwargs)

        self._originals["ball_instance_acreate"] = BallInstance.objects.acreate
        BallInstance.objects.acreate = patched_acreate  # type: ignore[assignment]

        # ── BallSpawnView.spawn ────────────────────────────────────────────────

        async def patched_spawn(view_self: BallSpawnView, channel: discord.TextChannel) -> bool:
            frame = get_active_frame(view_self.model.capacity_logic)
            if frame is not None:
                chance = frame.get("chance", 100)
                if not (isinstance(chance, int) and 1 <= chance <= 100 and random.randint(1, 100) <= chance):
                    # Chance failed — clear frame from in-memory capacity_logic so that
                    # patched_acreate / patched_ball_instance_save won't apply it on catch.
                    today_key = date.today().strftime("%m-%d-%Y")
                    temp = dict(view_self.model.capacity_logic)
                    temp.pop(today_key, None)
                    view_self.model.capacity_logic = temp
                    frame = None
            spawn_path: str | None = None
            if frame and frame.get("spawn"):
                spawn_path = f"./media/{frame['spawn']}"
                ext = frame["spawn"].rsplit(".", 1)[-1] if "." in frame["spawn"] else "png"
            else:
                ext = view_self.model.wild_card.name.split(".")[-1]

            file_name = f"nt_{_random_name()}.{ext}"
            try:
                permissions = channel.permissions_for(channel.guild.me)
                if permissions.attach_files and permissions.send_messages:
                    spawn_message = settings.get_random_message(PromptMessage.PromptType.SPAWN).format(
                        collectible=settings.collectible_name,
                        ball=view_self.name,
                        collectibles=settings.plural_collectible_name,
                        emoji=view_self.bot.get_emoji(view_self.model.emoji_id),
                    )
                    file_path = spawn_path or view_self.model.wild_card.path
                    await view_self.build(spawn_message, file_name, channel.guild.id)
                    view_self.message = await channel.send(
                        view=view_self,
                        file=discord.File(file_path, filename=file_name),
                    )
                    return True
                else:
                    log.warning("Missing permission to spawn ball in channel %s.", channel)
            except discord.Forbidden:
                log.warning("Missing permission to spawn ball in channel %s.", channel)
            except discord.HTTPException:
                log.error("Failed to spawn ball", exc_info=True)
            return False

        self._originals["spawn"] = BallSpawnView.spawn
        BallSpawnView.spawn = patched_spawn  # type: ignore[method-assign]

        # ── BallSpawnView.get_catch_message ────────────────────────────────────

        original_get_catch_message = BallSpawnView.get_catch_message

        def patched_get_catch_message(view_self: BallSpawnView, ball, new_ball, mention):
            message = original_get_catch_message(view_self, ball, new_ball, mention)
            frame = ball.extra_data if isinstance(ball.extra_data, dict) else None
            if frame and frame.get("catch"):
                message = f"{message}\n{frame['catch']}"
            return message

        self._originals["get_catch_message"] = BallSpawnView.get_catch_message
        BallSpawnView.get_catch_message = patched_get_catch_message  # type: ignore[method-assign]

        # ── draw_card ──────────────────────────────────────────────────────────

        self._originals["draw_card"] = image_gen_module.draw_card
        original_draw_card = image_gen_module.draw_card
        corners = image_gen_module.CORNERS
        artwork_size = image_gen_module.artwork_size
        credits_font = image_gen_module.credits_font
        get_credit_color = image_gen_module.get_credit_color
        credits_color_cache = image_gen_module.credits_color_cache
        HEIGHT = image_gen_module.HEIGHT
        credits_region = (0, 1840, image_gen_module.WIDTH, HEIGHT)

        def patched_draw_card(ball_instance):
            image, kwargs = original_draw_card(ball_instance)
            frame = ball_instance.extra_data if isinstance(ball_instance.extra_data, dict) else None
            if not frame:
                return image, kwargs

            # The decorations cog runs before us: it wraps the finished card in a larger
            # canvas, pasting it at a (margin // 2, margin // 2) offset before overlaying an
            # animated mask. So draw_card can hand us an already-padded (and multi-frame)
            # image, and every coordinate below has to be shifted by that same offset. The
            # vertical padding is the reliable signal — the canvas height is HEIGHT + margin
            # and the card sits at margin // 2 — so offset == (image.height - HEIGHT) // 2.
            # It resolves to 0 when no decoration is applied, leaving the plain-card path
            # untouched.
            offset = max(0, image.height - HEIGHT) // 2

            # A decoration turns the card into an animation; paint onto every frame it
            # produced, not just the first, so the frame art/credits don't flicker away.
            targets = kwargs.get("append_images") or [image]

            if frame.get("card"):
                try:
                    artwork = Image.open("./media/" + frame["card"]).convert("RGBA")
                    fitted = ImageOps.fit(artwork, artwork_size)
                    artwork.close()
                    position = (corners[0][0] + offset, corners[0][1] + offset)
                    for target in targets:
                        target.paste(fitted, position)  # type: ignore[arg-type]
                except Exception:
                    log.exception(
                        "Failed to apply frame card art for %s", ball_instance.countryball.country
                    )
            if frame.get("credits"):
                try:
                    ball = ball_instance.countryball
                    special_credits = ""
                    if ball_instance.specialcard and ball_instance.specialcard.credits:
                        special_credits = f" • Special Author: {ball_instance.specialcard.credits}"

                    # Wipe the original credits text by repainting the region with the
                    # untouched card background, then redraw it with the artwork author
                    # line swapped for the frame's credits.
                    background_path = ball_instance.special_card or ball.cached_regime.background
                    background = Image.open(background_path).convert("RGBA")
                    background_region = background.crop(credits_region)
                    background.close()

                    card_name = getattr(ball_instance.specialcard, "name", None) or ball.cached_regime.name
                    if card_name in credits_color_cache:
                        credits_color = credits_color_cache[card_name]
                    else:
                        credits_color = get_credit_color(
                            image, (0, int(image.height * 0.8), image.width, image.height)
                        )
                        credits_color_cache[card_name] = credits_color

                    paste_position = (credits_region[0] + offset, credits_region[1] + offset)
                    text_position = (30 + offset, 1870 + offset)
                    credits_text = (
                        f"Created by El Laggron{special_credits}\n"
                        f"Artwork author: {frame['credits']}"
                    )
                    for target in targets:
                        target.paste(background_region, paste_position)
                        ImageDraw.Draw(target).text(
                            text_position,
                            credits_text,
                            font=credits_font,
                            fill=credits_color,
                            stroke_width=0,
                            stroke_fill=(255, 255, 255, 255),
                        )
                except Exception:
                    log.exception(
                        "Failed to apply frame credits for %s", ball_instance.countryball.country
                    )

            # The decoration's animated mask was already composited onto these frames before
            # we pasted the frame art/credits, so our paint currently sits *over* it. Re-overlay
            # the mask (exactly as the decorations cog does) so the frame ends up underneath.
            if offset:
                try:
                    deco = ball_instance.entitlement.decoration
                except (ObjectDoesNotExist, AttributeError):
                    deco = None
                if deco is not None:
                    try:
                        animation = Image.open(deco.mask.path)
                        for target, mask_frame in zip(targets, ImageSequence.Iterator(animation)):
                            mask_frame.load()
                            resized = ImageOps.fit(mask_frame, target.size).convert("RGBA")
                            target.paste(resized, None, resized)
                        animation.close()
                    except Exception:
                        log.exception(
                            "Failed to re-overlay decoration for %s",
                            ball_instance.countryball.country,
                        )
            return image, kwargs

        image_gen_module.draw_card = patched_draw_card
        bd_models_module.draw_card = patched_draw_card

        # ── CountryballFormatter.format_page ───────────────────────────────────

        async def patched_format_page(fmt_self: CountryballFormatter, page) -> None:
            fmt_self.item.options = []
            async for ball in page:
                emoji = fmt_self.menu.bot.get_emoji(int(ball.countryball.emoji_id))
                favorite = f"{settings.favorited_collectible_emoji} " if ball.favorite else ""
                special = ball.specialcard.emoji if ball.specialcard else ""
                frame_entry = ball.extra_data if isinstance(ball.extra_data, dict) else None
                frame = "🖼️ " if isinstance(frame_entry, dict) and frame_entry.get("card") else ""
                fmt_self.item.add_option(
                    label=f"{favorite}{special}{frame}#{ball.pk:0X} {ball.countryball.country}",
                    description=(
                        f"ATK: {ball.attack}({ball.attack_bonus:+d}%) "
                        f"• HP: {ball.health}({ball.health_bonus:+d}%) • "
                        f"{ball.catch_date.strftime('%Y/%m/%d | %H:%M')}"
                    ),
                    emoji=emoji,
                    value=f"{ball.pk}",
                    default=ball.pk in fmt_self.defaulted,
                )
            fmt_self.min_values = max(fmt_self.min_values, len(page))
            fmt_self.item.max_values = min(fmt_self.max_values, len(page))

        self._originals["format_page"] = CountryballFormatter.format_page
        CountryballFormatter.format_page = patched_format_page  # type: ignore[method-assign]

        # ── FilteringChoices + filter_balls ───────────────────────────────────

        import ballsdex.core.utils.enums as enums_module
        import ballsdex.core.utils.sorting as sorting_module
        from ballsdex.core.utils.enums import FilteringChoices

        # Add the new enum member (only if not already present, e.g. reload safety)
        if not hasattr(FilteringChoices, "frame"):
            new_member = object.__new__(FilteringChoices)
            new_member._name_ = "frame"
            new_member._value_ = "frame"
            FilteringChoices._value2member_map_["frame"] = new_member  # type: ignore[attr-defined]
            FilteringChoices._member_map_["frame"] = new_member  # type: ignore[attr-defined]
            FilteringChoices._member_names_.append("frame")  # type: ignore[attr-defined]
            # EnumType blocks plain setattr for member names ("cannot reassign member"),
            # and newer Python no longer falls back to _member_map_ in __getattr__, so the
            # class attribute has to be set directly via the metaclass's type.__setattr__.
            type.__setattr__(FilteringChoices, "frame", new_member)

        original_filter_balls = sorting_module.filter_balls

        def patched_filter_balls(filter, queryset, guild_id=None):
            if filter == FilteringChoices.frame: # type: ignore
                return queryset.filter(extra_data__has_key="card")
            return original_filter_balls(filter, queryset, guild_id=guild_id)

        self._originals["filter_balls"] = sorting_module.filter_balls
        sorting_module.filter_balls = patched_filter_balls

        # re-bind in the balls cog's module if already imported
        try:
            import ballsdex.packages.balls.cog as balls_cog_module
            balls_cog_module.filter_balls = patched_filter_balls  # type: ignore[attr-defined]
            self._originals["balls_cog_filter_balls"] = original_filter_balls
        except Exception:
            pass

        log.info("Frames patches applied.")
