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
from django.urls import path as urlpath, reverse

from bd_models.models import Ball

from .models import FrameBall

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest, HttpResponse

FRAME_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")


def _is_frame_entry(value: Any) -> bool:
    return isinstance(value, dict) and bool({"card", "spawn", "credits", "catch"} & value.keys())


def _save_art(data: bytes, name: str) -> str:
    """Save bytes to MEDIA_ROOT, returning the stored path."""
    return default_storage.save(name, ContentFile(data))


# ── Forms ─────────────────────────────────────────────────────────────────────

class FrameAddForm(forms.Form):
    """Add form shown on the global 'Add Frame' page — includes a Ball picker."""

    ball = forms.ModelChoiceField(
        queryset=Ball.objects.all().order_by("country"),
        help_text="The countryball this frame applies to.",
    )
    date_from = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Start date for this frame. Only MM-DD-YYYY is stored. Use the end date for a range.",
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="End of date range — leave blank for a single day.",
    )
    spawn_art = forms.ImageField(
        required=False,
        help_text="Spawn art image (same format as a regular ball wild card). Leave blank to keep existing."
    )
    card_art = forms.ImageField(
        required=False,
        help_text="Collection card art image (same format as a regular ball collection card). Leave blank to keep existing."
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
        help_text="Probability (1–100) that this frame is applied on spawn. Defaults to 100 (always).",
    )

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        if date_from and date_to and date_to < date_from:
            self.add_error("date_to", "End date must be on or after the start date.")
        if cleaned.get("chance") is None:
            cleaned["chance"] = 100
        return cleaned


class FrameDateForm(forms.Form):
    """Form on the per-ball change page — ball is determined from the URL."""

    date_from = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Start date for this frame. Only MM-DD-YYYY is stored. Use the end date for a range.",
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="End of date range — leave blank for a single day.",
    )
    spawn_art = forms.ImageField(
        required=False,
        help_text="Spawn art image (same format as a regular ball wild card). Leave blank to keep existing."
    )
    card_art = forms.ImageField(
        required=False,
        help_text="Collection card art image (same format as a regular ball collection card). Leave blank to keep existing."
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
        help_text="Probability (1–100) that this frame is applied on spawn. Defaults to 100 (always).",
    )

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
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
) -> None:
    """
    Write MM-DD-YYYY frame entries into ball.capacity_logic and persist art files.
    spawn_bytes / card_bytes may be None — omitted keys are not added to the dict.
    Does NOT call ball.save().
    """
    safe_name = re.sub(r"[^a-z0-9]+", "_", ball.country.lower()).strip("_")
    capacity: dict[str, Any] = dict(ball.capacity_logic)

    current = date_from
    while current <= date_to:
        key = current.strftime("%m-%d-%Y")
        entry: dict[str, Any] = {
            "credits": credits_str,
            "catch": catch_str,
            "chance": chance,
        }
        if spawn_bytes is not None and spawn_ext is not None:
            entry["spawn"] = _save_art(spawn_bytes, f"frame_{safe_name}_{key}_spawn.{spawn_ext}")
        if card_bytes is not None and card_ext is not None:
            entry["card"] = _save_art(card_bytes, f"frame_{safe_name}_{key}_card.{card_ext}")
        capacity[key] = entry
        current += timedelta(days=1)

    ball.capacity_logic = capacity


# ── Admin ─────────────────────────────────────────────────────────────────────

@admin.register(FrameBall)
class FrameAdmin(admin.ModelAdmin):
    list_display = ("country", "frame_count", "frame_dates_display")
    ordering = ("country",)
    search_fields = ("country",)
    show_full_result_count = False

    # ── Queryset ──────────────────────────────────────────────────────────────

    def get_queryset(self, request: HttpRequest) -> QuerySet[Ball]:
        """Only show balls that have at least one valid MM-DD-YYYY frame entry."""
        return Ball.objects.annotate(
            has_frames=RawSQL(
                "EXISTS (SELECT 1 FROM jsonb_object_keys(capacity_logic) k WHERE k ~ %s)",
                (r"^\d{2}-\d{2}-\d{4}$",),
            )
        ).filter(has_frames=True)

    # ── Changelist columns ────────────────────────────────────────────────────

    @admin.display(description="Frames")
    def frame_count(self, obj: Ball) -> int:
        return sum(1 for k, v in obj.capacity_logic.items() if FRAME_DATE_RE.match(k) and _is_frame_entry(v))

    @admin.display(description="Dates (MM-DD-YYYY)")
    def frame_dates_display(self, obj: Ball) -> str:
        dates = sorted(k for k, v in obj.capacity_logic.items() if FRAME_DATE_RE.match(k) and _is_frame_entry(v))
        return ", ".join(dates) if dates else "—"

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
            ),
        ]
        return custom + super().get_urls()

    # ── Add view ──────────────────────────────────────────────────────────────

    def add_view(
        self,
        request: HttpRequest,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        if not self.has_add_permission(request):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied

        if request.method == "POST":
            form = FrameAddForm(request.POST, request.FILES)
            if form.is_valid():
                ball: Ball = form.cleaned_data["ball"]
                date_from: date = form.cleaned_data["date_from"]
                date_to: date = form.cleaned_data.get("date_to") or date_from
                spawn_file = form.cleaned_data.get("spawn_art")
                card_file = form.cleaned_data.get("card_art")
                spawn_bytes = spawn_file.read() if spawn_file else None
                spawn_ext = (spawn_file.name.rsplit(".", 1)[-1] if "." in spawn_file.name else "png") if spawn_file else None
                card_bytes = card_file.read() if card_file else None
                card_ext = (card_file.name.rsplit(".", 1)[-1] if "." in card_file.name else "png") if card_file else None

                _apply_frames(
                    ball, date_from, date_to,
                    spawn_bytes, spawn_ext,
                    card_bytes, card_ext,
                    form.cleaned_data["credits"],
                    form.cleaned_data["catch_phrase"],
                    form.cleaned_data.get("chance", 100),
                )
                ball.save(update_fields=["capacity_logic"])

                date_label = (
                    f"{date_from:%m-%d-%Y} → {date_to:%m-%d-%Y}" if date_to != date_from else f"{date_from:%m-%d-%Y}"
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
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        ball = get_object_or_404(Ball, pk=object_id)

        if request.method == "POST":
            form = FrameDateForm(request.POST, request.FILES)
            if form.is_valid():
                date_from: date = form.cleaned_data["date_from"]
                date_to: date = form.cleaned_data.get("date_to") or date_from
                spawn_file = form.cleaned_data.get("spawn_art")
                card_file = form.cleaned_data.get("card_art")
                spawn_bytes = spawn_file.read() if spawn_file else None
                spawn_ext = (spawn_file.name.rsplit(".", 1)[-1] if "." in spawn_file.name else "png") if spawn_file else None
                card_bytes = card_file.read() if card_file else None
                card_ext = (card_file.name.rsplit(".", 1)[-1] if "." in card_file.name else "png") if card_file else None

                _apply_frames(
                    ball, date_from, date_to,
                    spawn_bytes, spawn_ext,
                    card_bytes, card_ext,
                    form.cleaned_data["credits"],
                    form.cleaned_data["catch_phrase"],
                    form.cleaned_data.get("chance", 100),
                )
                ball.save(update_fields=["capacity_logic"])

                date_label = (
                    f"{date_from:%m-%d-%Y} → {date_to:%m-%d-%Y}" if date_to != date_from else f"{date_from:%m-%d-%Y}"
                )
                self.message_user(request, f"Updated frames for {ball.country}: {date_label}.")
                return redirect(".")
        else:
            form = FrameDateForm()

        frames = [
            {
                "date": k,
                "data": v,
                "card_url": f"/media/{v['card']}" if isinstance(v, dict) and v.get("card") else "",
                "spawn_url": f"/media/{v['spawn']}" if isinstance(v, dict) and v.get("spawn") else "",
            }
            for k, v in sorted(ball.capacity_logic.items())
            if FRAME_DATE_RE.match(k) and _is_frame_entry(v)
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

    def delete_date_view(
        self, request: HttpRequest, ball_pk: int, date_key: str
    ) -> HttpResponse:
        if not self.has_change_permission(request):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied

        if not FRAME_DATE_RE.match(date_key):
            self.message_user(request, f"Invalid date key: {date_key!r}.", level=messages.ERROR)
            return redirect(reverse("admin:frames_frameball_changelist"))

        ball = get_object_or_404(Ball, pk=ball_pk)
        capacity: dict[str, Any] = dict(ball.capacity_logic)

        if date_key not in capacity:
            self.message_user(
                request,
                f"Frame {date_key} not found on {ball.country}.",
                level=messages.WARNING,
            )
        else:
            capacity.pop(date_key)
            ball.capacity_logic = capacity
            ball.save(update_fields=["capacity_logic"])
            self.message_user(request, f"Removed frame {date_key} from {ball.country}.")

        return redirect(reverse("admin:frames_frameball_change", args=[ball_pk]))
