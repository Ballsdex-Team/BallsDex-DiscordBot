from __future__ import annotations

import logging
import os
import random
import string
from contextvars import ContextVar
from datetime import date
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

from ..utils import frames_depend_on_special, pick_frame

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot
    from ballsdex.packages.countryballs.countryball import BallSpawnView
    from bd_models.models import BallInstance

log = logging.getLogger("ballsdex.packages.frames")

# the spawn being caught, while the treasure caught from it is created
catching: ContextVar[BallSpawnView | None] = ContextVar("frames_catching", default=None)
# the picked_frame of a spawn once its treasure got it
NOT_PICKED: Any = object()


def _random_name() -> str:
    source = string.ascii_uppercase + string.ascii_lowercase + string.ascii_letters
    return "".join(random.choices(source, k=15))


def pick_spawn_frame(view: BallSpawnView) -> dict | None:
    """
    The frame shown by a spawn. The treasure caught from it gets the same frame, see `frame_of_new_treasure`.
    """
    if view.ballinstance is not None:
        # a dropped treasure keeps its own frame
        return view.ballinstance.extra_data if view.ballinstance.framed else None
    today = date.today()
    special = view.special
    if special is None and frames_depend_on_special(view.model.capacity_logic, today):
        # the frame depends on the special, which is rolled at catch: roll it now for the spawn to show its frame,
        # and make the catch keep it, even when there is none
        special = view.get_random_special()
        view.get_random_special = lambda: special  # type: ignore[method-assign]
    view.picked_frame = pick_frame(view.model.capacity_logic, special.pk if special else None, today)  # type: ignore[attr-defined]
    return view.picked_frame  # type: ignore[attr-defined]


def frame_of_new_treasure(instance: BallInstance) -> dict | None:
    """
    The frame a treasure gets when it is created: the one picked when it spawned if it was caught, else the frame of
    its special (or of the treasures without special) or of every treasure for today, with their chance.
    """
    view = catching.get()
    if view is not None and view.model.pk == instance.ball_id:
        picked = getattr(view, "picked_frame", NOT_PICKED)
        if picked is not NOT_PICKED:
            # only for the treasure of this catch
            view.picked_frame = NOT_PICKED  # type: ignore[attr-defined]
            return picked
    return pick_frame(instance.ball.capacity_logic, instance.special_id, date.today())


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
        from ballsdex.core.utils.enums import FilteringChoices
        from bd_models.models import BallInstance

        if "spawn" in self._originals:
            BallSpawnView.spawn = self._originals["spawn"]  # type: ignore[method-assign]
        if "catch_ball" in self._originals:
            BallSpawnView.catch_ball = self._originals["catch_ball"]  # type: ignore[method-assign]
        if "get_catch_message" in self._originals:
            BallSpawnView.get_catch_message = self._originals["get_catch_message"]  # type: ignore[method-assign]
        if "draw_card" in self._originals:
            image_gen_module.draw_card = self._originals["draw_card"]
            bd_models_module.draw_card = self._originals["draw_card"]
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
        from ballsdex.packages.countryballs.countryball import BallSpawnView
        from settings.models import PromptMessage, settings
        from bd_models.models import BallInstance

        # ── BallInstance.save ──────────────────────────────────────────────────
        # every new treasure goes through it: catches, packs, claims, gifts from admins...

        original_ball_instance_save = BallInstance.save

        def patched_ball_instance_save(self, *args, **kwargs):
            if not self.pk and not self.extra_data:
                try:
                    frame = frame_of_new_treasure(self)
                    if frame is not None:
                        self.extra_data = frame
                except Exception:
                    log.exception("Failed to pick the frame of a new %s", self.ball_id)
            return original_ball_instance_save(self, *args, **kwargs)

        self._originals["ball_instance_save"] = BallInstance.save
        BallInstance.save = patched_ball_instance_save  # type: ignore[method-assign]

        # ── BallSpawnView.spawn ────────────────────────────────────────────────

        async def patched_spawn(view_self: BallSpawnView, channel: discord.TextChannel) -> bool:
            frame = pick_spawn_frame(view_self)
            spawn_path: str | None = None
            if frame and frame.get("spawn") and os.path.isfile(f"./media/{frame['spawn']}"):
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

        # ── BallSpawnView.catch_ball ───────────────────────────────────────────

        original_catch_ball = BallSpawnView.catch_ball

        async def patched_catch_ball(view_self: BallSpawnView, *args, **kwargs):
            # the treasure created by the catch gets the frame picked by the spawn, see frame_of_new_treasure
            token = catching.set(view_self)
            try:
                return await original_catch_ball(view_self, *args, **kwargs)
            finally:
                catching.reset(token)

        self._originals["catch_ball"] = BallSpawnView.catch_ball
        BallSpawnView.catch_ball = patched_catch_ball  # type: ignore[method-assign]

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

        def patched_draw_card(ball_instance, **options):
            frame = ball_instance.extra_data if isinstance(ball_instance.extra_data, dict) else None
            if not frame:
                return original_draw_card(ball_instance, **options)
            if frame.get("card"):
                # either the whole card, or only the artwork square
                layout = "full_art" if frame.get("full_art") else "artwork"
                options.setdefault(layout, "./media/" + frame["card"])
            if frame.get("credits"):
                options.setdefault("artwork_credits", frame["credits"])
            try:
                return original_draw_card(ball_instance, **options)
            except Exception:
                log.exception("Failed to apply the frame of %s, drawing the regular card", ball_instance.pk)
                return original_draw_card(ball_instance)

        image_gen_module.draw_card = patched_draw_card
        bd_models_module.draw_card = patched_draw_card

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
