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

from ballsdex.core.utils import checks
from ballsdex.core.utils.transformers import BallEnabledTransform

from ..utils import (
    NO_SPECIAL,
    frame_label,
    frames_depend_on_special,
    is_named_key,
    iter_frames,
    parse_frame_key,
    pick_frame,
)

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
        import ballsdex.core.utils.sorting as sorting_module
        import bd_models.models as bd_models_module
        from ballsdex.core.utils.enums import FilteringChoices
        from ballsdex.packages.countryballs.countryball import BallSpawnView
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
        from bd_models.models import BallInstance
        from settings.models import PromptMessage, settings

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
                        view=view_self, file=discord.File(file_path, filename=file_name)
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
            if filter == FilteringChoices.frame:  # type: ignore
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


# ── Commands ──────────────────────────────────────────────────────────────────


def _today_keys(day: date) -> tuple[str, str]:
    """The plain key of a day and the prefix its per-special frames use."""
    stamp = day.strftime("%m-%d-%Y")
    return stamp, stamp + ":"


def _frame_line(ball_name: str, key: str, entry: dict, special_names: dict[int, str]) -> str:
    """
    One frame as staff read it: what it is called, what it is stored under, and who can get it.

    `ball_name` is left out when the listing is already about one treasure.
    """
    label = frame_label(key, entry)
    shown = f"{entry['emoji']} {label}" if entry.get("emoji") else label
    bits = [f"**{ball_name}** — {shown}" if ball_name else shown]
    if label != key:
        bits.append(f"`{key}`")
    parsed = parse_frame_key(key)
    if parsed is not None and parsed[1] is not None:
        target = "no special" if parsed[1] == NO_SPECIAL else special_names.get(parsed[1], f"special #{parsed[1]}")
        bits.append(f"for {target}")
    chance = entry.get("chance", 100)
    if isinstance(chance, int) and chance != 100:
        bits.append(f"{chance}%")
    if entry.get("full_art"):
        bits.append("full art")
    return " · ".join(bits)


async def _special_names() -> dict[int, str]:
    from bd_models.models import Special

    return {pk: name async for pk, name in Special.objects.values_list("pk", "name")}


def _send_lines(header: str, lines: list[str], empty: str) -> str:
    """
    The listing as one message, trimmed to what Discord accepts rather than paginated: a frame listing is for
    staff checking a handful of events, not something to browse.
    """
    if not lines:
        return f"{header}\n-# {empty}"
    text = header
    for index, line in enumerate(lines):
        if len(text) + len(line) > 1900:
            return text + f"\n-# …and {len(lines) - index} more."
        text += f"\n- {line}"
    return text


class FrameCommands(commands.Cog):
    """
    Looking at the frames from Discord, so staff do not have to open the admin to answer "what is live today?".
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @commands.hybrid_group(name="frames")
    @checks.has_permissions("bd_models.change_ball")
    async def frames_group(self, ctx: commands.Context[BallsDexBot]):
        """
        Frames: the alternate art a treasure can wear.
        """
        await ctx.send_help(ctx.command)

    @frames_group.command(name="active")
    @checks.has_permissions("bd_models.change_ball")
    async def frames_active(self, ctx: commands.Context[BallsDexBot]):
        """
        The frames running today, the ones a catch can roll right now.
        """
        await ctx.defer(ephemeral=True)
        from bd_models.models import balls

        today = date.today()
        plain, prefix = _today_keys(today)
        names = await _special_names()
        lines = []
        for ball in balls.values():
            for key, entry in iter_frames(ball.capacity_logic):
                if key == plain or key.startswith(prefix):
                    lines.append(_frame_line(ball.country, key, entry, names))
        lines.sort()
        header = f"## Frames running today ({today:%d/%m/%Y})"
        await ctx.send(
            _send_lines(header, lines, "Nothing is running today. Named frames are still givable, see /frames named."),
            ephemeral=True,
        )

    @frames_group.command(name="named")
    @checks.has_permissions("bd_models.change_ball")
    async def frames_named(self, ctx: commands.Context[BallsDexBot]):
        """
        The frames with a name and no date: they never drop, they are only given on purpose.
        """
        await ctx.defer(ephemeral=True)
        from bd_models.models import balls

        names = await _special_names()
        lines = []
        for ball in balls.values():
            for key, entry in iter_frames(ball.capacity_logic):
                if is_named_key(key):
                    lines.append(_frame_line(ball.country, key, entry, names))
        lines.sort()
        header = "## Named frames\n-# Never rolled on a catch: give them as a pass reward or with an admin spawn."
        await ctx.send(_send_lines(header, lines, "No named frame yet."), ephemeral=True)

    @frames_group.command(name="of")
    @checks.has_permissions("bd_models.change_ball")
    async def frames_of(self, ctx: commands.Context[BallsDexBot], *, countryball: BallEnabledTransform):
        """
        Every frame of one treasure, whatever its date.

        Parameters
        ----------
        countryball: Ball
            The treasure to look at.
        """
        await ctx.defer(ephemeral=True)
        names = await _special_names()
        lines = sorted(_frame_line("", key, entry, names) for key, entry in iter_frames(countryball.capacity_logic))
        header = f"## Frames of {countryball.country}"
        await ctx.send(_send_lines(header, lines, "This treasure has no frame."), ephemeral=True)
