from __future__ import annotations

import re
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from django import forms
from django.contrib import admin, messages
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models.expressions import RawSQL
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path as urlpath
from django.urls import reverse

from bd_models.models import FRAME_SPECIAL_NAME, Ball, Special

from .models import FrameBall
from .utils import NO_SPECIAL, frame_key, is_frame_entry, is_named_key, parse_frame_key, slugify_frame_name

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest, HttpResponse

# a frame is recognised by what it holds rather than by its key, so the dated and the named ones both count
HAS_FRAME_SQL = "EXISTS (SELECT 1 FROM jsonb_each(capacity_logic) e WHERE e.value ? 'card' OR e.value ? 'spawn')"
CARD_LAYOUTS = (("artwork", "Artwork square"), ("full_art", "Full art (whole card)"))


def _extension(upload) -> str | None:
    """The file extension of an upload, defaulting to png, or None when nothing was uploaded."""
    if not upload:
        return None
    return upload.name.rsplit(".", 1)[-1] if "." in upload.name else "png"


def _save_art(data: bytes, name: str) -> str:
    """Save bytes to MEDIA_ROOT, returning the stored path."""
    return default_storage.save(name, ContentFile(data))


NO_SPECIAL_LABEL = "No special"


def _special_choices() -> list[tuple[str, str]]:
    # the "Frame" special selects the framed treasures in the commands, it is never given to a treasure
    specials = Special.objects.exclude(name__iexact=FRAME_SPECIAL_NAME).order_by("name").values_list("pk", "name")
    return [("", "Every treasure"), (str(NO_SPECIAL), f"{NO_SPECIAL_LABEL} (regular treasures only)")] + [
        (str(pk), name) for pk, name in specials
    ]


def _special_field() -> forms.TypedChoiceField:
    return forms.TypedChoiceField(
        choices=_special_choices,
        coerce=int,
        empty_value=None,
        required=False,
        help_text="Only the treasures of this special get the frame, or only the treasures without special. On the "
        "same day, these frames go before the frame of every treasure.",
    )


def _special_label(special_id: int | None, names: dict[int, str]) -> str | None:
    if special_id is None:
        return None
    if special_id == NO_SPECIAL:
        return NO_SPECIAL_LABEL
    return names.get(special_id, f"deleted special #{special_id}")


def _frame_label(day: str, special: str | None) -> str:
    return f"{day} ({special})" if special else day


def _frames_of(ball: Ball) -> list[dict[str, Any]]:
    """
    The frames of a ball, by date: the frame of every treasure, then the one of the treasures without special, then
    the frames of a special.
    """
    frames: list[dict[str, Any]] = []
    for key, value in ball.capacity_logic.items():
        if not is_frame_entry(value):
            continue
        parsed = parse_frame_key(key)
        if parsed is not None:
            frames.append({"key": key, "date": parsed[0], "special_id": parsed[1], "data": value})
        elif is_named_key(key):
            # a named frame has no day: it never drops, it is only given on purpose
            frames.append({"key": key, "date": "", "special_id": None, "data": value})
    special_ids = {x["special_id"] for x in frames if x["special_id"]}
    names = dict(Special.objects.filter(pk__in=special_ids).values_list("pk", "name")) if special_ids else {}
    for frame in frames:
        frame["special"] = _special_label(frame["special_id"], names)
        frame["name"] = str(frame["data"].get("name") or "")
        if frame["date"]:
            frame["label"] = _frame_label(frame["date"], frame["special"])
            if frame["name"]:
                frame["label"] = f"{frame['name']} — {frame['label']}"
        else:
            frame["label"] = f"{frame['name'] or frame['key']} (no date)"
    frames.sort(key=_frame_order)
    return frames


def _frame_order(frame: dict[str, Any]) -> tuple:
    day, special_id = frame["date"], frame["special_id"]
    target = 0 if special_id is None else 1 if special_id == NO_SPECIAL else 2
    # the named frames have no day, they are listed first; the dated ones go by year, then month and day
    return ("" if not day else "1", day[6:], day[:5], target, frame["special"] or "", frame["key"])


# ── Forms ─────────────────────────────────────────────────────────────────────


class FrameAddForm(forms.Form):
    """Add form shown on the global 'Add Frame' page — includes a Ball picker."""

    ball = forms.ModelChoiceField(
        queryset=Ball.objects.all().order_by("country"), help_text="The countryball this frame applies to."
    )
    name = forms.CharField(
        max_length=64,
        required=False,
        help_text="What this frame is called, shown to players on a framed treasure and used to give it as a "
        'reward: a pass can then ask for "Haki" instead of a date. Required for a frame with no date.',
    )
    emoji = forms.CharField(
        max_length=64,
        required=False,
        help_text="Shown next to the name on a framed treasure. Write a server emoji in full, like <:Haki:1234567890>.",
    )
    no_date = forms.BooleanField(
        required=False,
        label="No date",
        help_text="A frame with no date never drops on a catch. It is only given on purpose, as a pass reward or "
        "with an admin spawn. The dates below are then ignored.",
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="First day the frame can drop. Only MM-DD-YYYY is stored. Use the end date for a range, or "
        'tick "No date" above for a frame that never drops.',
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="End of date range — leave blank for a single day.",
    )
    special = _special_field()
    spawn_art = forms.ImageField(
        required=False,
        help_text="Spawn art image (same format as a regular ball wild card). Leave blank to keep existing.",
    )
    card_art = forms.ImageField(
        required=False,
        help_text="Collection card art image (same format as a regular ball collection card). "
        "Leave blank to keep existing.",
    )
    card_layout = forms.ChoiceField(
        choices=CARD_LAYOUTS,
        initial="artwork",
        widget=forms.RadioSelect,
        help_text="Where the card art goes: in the artwork square of the regular card, or over the whole card "
        "with the name, ability and stats written on top.",
    )
    credits = forms.CharField(max_length=256, help_text="Artwork credits line.")
    catch_phrase = forms.CharField(
        max_length=512,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Text appended to the catch message during this frame window.",
    )
    chance = forms.IntegerField(
        min_value=1,
        max_value=100,
        initial=100,
        required=False,
        help_text="Probability (1–100) that a new treasure gets this frame, decided when it spawns. "
        "Defaults to 100 (always).",
    )

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        if cleaned.get("no_date"):
            if not (cleaned.get("name") or "").strip():
                self.add_error("name", "A frame with no date needs a name: that name is how you give it.")
        elif not date_from:
            self.add_error("date_from", 'Give a start date, or tick "No date" for a frame that never drops.')
        if date_from and date_to and date_to < date_from:
            self.add_error("date_to", "End date must be on or after the start date.")
        if cleaned.get("chance") is None:
            cleaned["chance"] = 100
        return cleaned


class FrameDateForm(forms.Form):
    """Form on the per-ball change page — ball is determined from the URL."""

    name = forms.CharField(
        max_length=64,
        required=False,
        help_text="What this frame is called, shown to players on a framed treasure and used to give it as a "
        'reward: a pass can then ask for "Haki" instead of a date. Required for a frame with no date.',
    )
    emoji = forms.CharField(
        max_length=64,
        required=False,
        help_text="Shown next to the name on a framed treasure. Write a server emoji in full, like <:Haki:1234567890>.",
    )
    no_date = forms.BooleanField(
        required=False,
        label="No date",
        help_text="A frame with no date never drops on a catch. It is only given on purpose, as a pass reward or "
        "with an admin spawn. The dates below are then ignored.",
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="First day the frame can drop. Only MM-DD-YYYY is stored. Use the end date for a range, or "
        'tick "No date" above for a frame that never drops.',
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="End of date range — leave blank for a single day.",
    )
    special = _special_field()
    spawn_art = forms.ImageField(
        required=False,
        help_text="Spawn art image (same format as a regular ball wild card). Leave blank to keep existing.",
    )
    card_art = forms.ImageField(
        required=False,
        help_text="Collection card art image (same format as a regular ball collection card). "
        "Leave blank to keep existing.",
    )
    card_layout = forms.ChoiceField(
        choices=CARD_LAYOUTS,
        initial="artwork",
        widget=forms.RadioSelect,
        help_text="Where the card art goes: in the artwork square of the regular card, or over the whole card "
        "with the name, ability and stats written on top.",
    )
    credits = forms.CharField(max_length=256, help_text="Artwork credits line.")
    catch_phrase = forms.CharField(
        max_length=512,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Text appended to the catch message during this frame window.",
    )
    chance = forms.IntegerField(
        min_value=1,
        max_value=100,
        initial=100,
        required=False,
        help_text="Probability (1–100) that a new treasure gets this frame, decided when it spawns. "
        "Defaults to 100 (always).",
    )

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        if cleaned.get("no_date"):
            if not (cleaned.get("name") or "").strip():
                self.add_error("name", "A frame with no date needs a name: that name is how you give it.")
        elif not date_from:
            self.add_error("date_from", 'Give a start date, or tick "No date" for a frame that never drops.')
        if date_from and date_to and date_to < date_from:
            self.add_error("date_to", "End date must be on or after the start date.")
        if cleaned.get("chance") is None:
            cleaned["chance"] = 100
        return cleaned


# ── Helpers ───────────────────────────────────────────────────────────────────


def _apply_frames(
    ball: Ball,
    date_from: date,
    date_to: date,
    spawn_bytes: bytes | None,
    spawn_ext: str | None,
    card_bytes: bytes | None,
    card_ext: str | None,
    credits_str: str,
    catch_str: str,
    chance: int = 100,
    full_art: bool = False,
    special_id: int | None = None,
    name: str = "",
    emoji: str = "",
    no_date: bool = False,
) -> None:
    """
    Write the frame entries into ball.capacity_logic and persist art files.

    A dated frame writes one entry per day: "MM-DD-YYYY" for every treasure, "MM-DD-YYYY:<special id>" for the
    treasures of a special, "MM-DD-YYYY:0" without special. With `no_date` a single entry is written under the
    slug of its name instead, which no catch ever rolls — it is only given on purpose.

    spawn_bytes / card_bytes may be None: an entry that already has art keeps it.
    Does NOT call ball.save().
    """
    safe_name = re.sub(r"[^a-z0-9]+", "_", ball.country.lower()).strip("_")
    capacity: dict[str, Any] = dict(ball.capacity_logic)
    keys = [slugify_frame_name(name)] if no_date else _dated_keys(date_from, date_to, special_id)

    for key in keys:
        file_key = key.replace(":", "_")
        previous = capacity.get(key) if is_frame_entry(capacity.get(key)) else {}
        entry: dict[str, Any] = {"credits": credits_str, "catch": catch_str, "chance": chance, "full_art": full_art}
        if name:
            entry["name"] = name
        if emoji:
            entry["emoji"] = emoji
        if spawn_bytes is not None and spawn_ext is not None:
            entry["spawn"] = _save_art(spawn_bytes, f"frame_{safe_name}_{file_key}_spawn.{spawn_ext}")
        elif previous.get("spawn"):
            entry["spawn"] = previous["spawn"]
        if card_bytes is not None and card_ext is not None:
            entry["card"] = _save_art(card_bytes, f"frame_{safe_name}_{file_key}_card.{card_ext}")
        elif previous.get("card"):
            entry["card"] = previous["card"]
        capacity[key] = entry

    ball.capacity_logic = capacity


def _dated_keys(date_from: date, date_to: date, special_id: int | None) -> list[str]:
    """Every day of the range, as the key its frame is stored under."""
    keys, current = [], date_from
    while current <= date_to:
        keys.append(frame_key(current, special_id))
        current += timedelta(days=1)
    return keys


def _saved_frames_label(
    date_from: date, date_to: date, special_id: int | None, name: str = "", no_date: bool = False
) -> str:
    if no_date:
        return f"{name} (no date, given on purpose only)"
    dates = f"{date_from:%m-%d-%Y} → {date_to:%m-%d-%Y}" if date_to != date_from else f"{date_from:%m-%d-%Y}"
    names = dict(Special.objects.filter(pk=special_id).values_list("pk", "name")) if special_id else {}
    label = _frame_label(dates, _special_label(special_id, names))
    return f"{name} — {label}" if name else label


# ── Admin ─────────────────────────────────────────────────────────────────────


@admin.register(FrameBall)
class FrameAdmin(admin.ModelAdmin):
    list_display = ("country", "frame_count", "frame_dates_display")
    ordering = ("country",)
    search_fields = ("country",)
    show_full_result_count = False

    # ── Queryset ──────────────────────────────────────────────────────────────

    def get_queryset(self, request: HttpRequest) -> QuerySet[Ball]:
        """Only show balls that have at least one frame entry."""
        return Ball.objects.annotate(has_frames=RawSQL(HAS_FRAME_SQL, ())).filter(has_frames=True)

    # ── Changelist columns ────────────────────────────────────────────────────

    @admin.display(description="Frames")
    def frame_count(self, obj: Ball) -> int:
        return len(_frames_of(obj))

    @admin.display(description="Frames (name, then date MM-DD-YYYY)")
    def frame_dates_display(self, obj: Ball) -> str:
        return ", ".join(x["label"] for x in _frames_of(obj)) or "—"

    # ── Permissions ───────────────────────────────────────────────────────────

    def has_delete_permission(self, request: HttpRequest, obj: Ball | None = None) -> bool:
        # Individual frame dates are removed via delete_date_view, not the Django delete action.
        return False

    # ── Custom URLs ───────────────────────────────────────────────────────────

    def get_urls(self):
        custom = [
            urlpath(
                "<int:ball_pk>/delete_date/<str:date_key>/",
                self.admin_site.admin_view(self.delete_date_view),
                name="frames_frameball_delete_date",
            )
        ]
        return custom + super().get_urls()

    # ── Add view ──────────────────────────────────────────────────────────────

    def add_view(
        self, request: HttpRequest, form_url: str = "", extra_context: dict[str, Any] | None = None
    ) -> HttpResponse:
        if not self.has_add_permission(request):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied

        if request.method == "POST":
            form = FrameAddForm(request.POST, request.FILES)
            if form.is_valid():
                ball: Ball = form.cleaned_data["ball"]
                no_date: bool = bool(form.cleaned_data.get("no_date"))
                # a dateless frame still needs a day to satisfy the signature; nothing reads it
                date_from: date = form.cleaned_data.get("date_from") or date.today()
                date_to: date = form.cleaned_data.get("date_to") or date_from
                special_id: int | None = form.cleaned_data.get("special")
                spawn_file = form.cleaned_data.get("spawn_art")
                card_file = form.cleaned_data.get("card_art")
                spawn_bytes = spawn_file.read() if spawn_file else None
                spawn_ext = _extension(spawn_file)
                card_bytes = card_file.read() if card_file else None
                card_ext = _extension(card_file)

                _apply_frames(
                    ball,
                    date_from,
                    date_to,
                    spawn_bytes,
                    spawn_ext,
                    card_bytes,
                    card_ext,
                    form.cleaned_data["credits"],
                    form.cleaned_data["catch_phrase"],
                    form.cleaned_data.get("chance", 100),
                    form.cleaned_data.get("card_layout") == "full_art",
                    special_id,
                    name=(form.cleaned_data.get("name") or "").strip(),
                    emoji=(form.cleaned_data.get("emoji") or "").strip(),
                    no_date=no_date,
                )
                ball.save(update_fields=["capacity_logic"])

                date_label = _saved_frames_label(
                    date_from, date_to, special_id, (form.cleaned_data.get("name") or "").strip(), no_date
                )
                self.message_user(request, f"Added frame(s) for {ball.country}: {date_label}.")
                return redirect(reverse("admin:frames_frameball_changelist"))
        else:
            form = FrameAddForm()

        context = {
            **self.admin_site.each_context(request),
            "title": "Add Frame",
            "form": form,
            "opts": self.model._meta,
            "add": True,
            "change": False,
            "is_popup": False,
            "save_as": False,
            "has_add_permission": self.has_add_permission(request),
            "has_change_permission": False,
            "has_view_permission": self.has_view_permission(request),
            "has_delete_permission": False,
            "has_editable_inline_admin_formsets": False,
            "media": self.media,
            **(extra_context or {}),
        }
        return render(request, "admin/frames/frameball/add_form.html", context)

    # ── Change view ───────────────────────────────────────────────────────────

    def change_view(
        self, request: HttpRequest, object_id: str, form_url: str = "", extra_context: dict[str, Any] | None = None
    ) -> HttpResponse:
        ball = get_object_or_404(Ball, pk=object_id)

        if request.method == "POST":
            form = FrameDateForm(request.POST, request.FILES)
            if form.is_valid():
                no_date: bool = bool(form.cleaned_data.get("no_date"))
                # a dateless frame still needs a day to satisfy the signature; nothing reads it
                date_from: date = form.cleaned_data.get("date_from") or date.today()
                date_to: date = form.cleaned_data.get("date_to") or date_from
                special_id: int | None = form.cleaned_data.get("special")
                spawn_file = form.cleaned_data.get("spawn_art")
                card_file = form.cleaned_data.get("card_art")
                spawn_bytes = spawn_file.read() if spawn_file else None
                spawn_ext = _extension(spawn_file)
                card_bytes = card_file.read() if card_file else None
                card_ext = _extension(card_file)

                _apply_frames(
                    ball,
                    date_from,
                    date_to,
                    spawn_bytes,
                    spawn_ext,
                    card_bytes,
                    card_ext,
                    form.cleaned_data["credits"],
                    form.cleaned_data["catch_phrase"],
                    form.cleaned_data.get("chance", 100),
                    form.cleaned_data.get("card_layout") == "full_art",
                    special_id,
                    name=(form.cleaned_data.get("name") or "").strip(),
                    emoji=(form.cleaned_data.get("emoji") or "").strip(),
                    no_date=no_date,
                )
                ball.save(update_fields=["capacity_logic"])

                date_label = _saved_frames_label(
                    date_from, date_to, special_id, (form.cleaned_data.get("name") or "").strip(), no_date
                )
                self.message_user(request, f"Updated frames for {ball.country}: {date_label}.")
                return redirect(".")
        else:
            form = FrameDateForm()

        frames = [
            {
                **frame,
                "card_url": f"/media/{frame['data']['card']}" if frame["data"].get("card") else "",
                "spawn_url": f"/media/{frame['data']['spawn']}" if frame["data"].get("spawn") else "",
            }
            for frame in _frames_of(ball)
        ]

        context = {
            **self.admin_site.each_context(request),
            "title": f"Frames: {ball.country}",
            "ball": ball,
            "frames": frames,
            "form": form,
            "opts": self.model._meta,
            "original": ball,
            "object_id": object_id,
            "add": False,
            "change": True,
            "is_popup": False,
            "save_as": False,
            "has_add_permission": self.has_add_permission(request),
            "has_change_permission": self.has_change_permission(request, ball),
            "has_view_permission": self.has_view_permission(request, ball),
            "has_delete_permission": False,
            "has_editable_inline_admin_formsets": False,
            "media": self.media,
            **(extra_context or {}),
        }
        return render(request, "admin/frames/frameball/change_form.html", context)

    # ── Delete date view ──────────────────────────────────────────────────────

    def delete_date_view(self, request: HttpRequest, ball_pk: int, date_key: str) -> HttpResponse:
        if not self.has_change_permission(request):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied

        if parse_frame_key(date_key) is None:
            self.message_user(request, f"Invalid date key: {date_key!r}.", level=messages.ERROR)
            return redirect(reverse("admin:frames_frameball_changelist"))

        ball = get_object_or_404(Ball, pk=ball_pk)
        capacity: dict[str, Any] = dict(ball.capacity_logic)
        label = next((x["label"] for x in _frames_of(ball) if x["key"] == date_key), date_key)

        if date_key not in capacity:
            self.message_user(request, f"Frame {label} not found on {ball.country}.", level=messages.WARNING)
        else:
            capacity.pop(date_key)
            ball.capacity_logic = capacity
            ball.save(update_fields=["capacity_logic"])
            self.message_user(request, f"Removed frame {label} from {ball.country}.")

        return redirect(reverse("admin:frames_frameball_change", args=[ball_pk]))
