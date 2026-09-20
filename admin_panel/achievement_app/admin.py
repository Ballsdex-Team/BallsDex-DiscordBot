import json
from typing import TYPE_CHECKING, Any

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.widgets import AutocompleteSelect
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django_admin_action_forms import AdminActionForm, action_with_form

from .models import Achievement, AchievementCategory, AchievementType, PlayerAchievementStats, UserAchievement
from .recompute import RECOMPUTABLE_TYPES, recompute_progress
from .types import PARAMETER_FIELDS, TYPES, goal_text

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest


def rendered_widgets(field: forms.Field) -> list[forms.Widget]:
    """
    The widgets an attribute must be set on to reach the HTML.

    A foreign key is wrapped in a `RelatedFieldWidgetWrapper` (the add/change icons next to the field), and the
    wrapper renders the real widget with the real widget's own attributes: anything set on the wrapper alone never
    reaches the page. The form also deep copies its fields, so the two no longer share their attribute dict.
    """
    widget = field.widget
    inner = getattr(widget, "widget", None)
    return [widget, inner] if isinstance(inner, forms.Widget) else [widget]


def configure_parameter_widgets(form: forms.BaseForm):
    """
    Tag every setting field with the types using it, the admin script only shows the relevant ones.
    """
    for name in PARAMETER_FIELDS:
        if name not in form.fields:
            continue
        # hidden settings may not be submitted, they fall back to their default value when cleaned
        form.fields[name].required = False
        types = [definition.type.value for definition in TYPES.values() if name in definition.fields]
        for widget in rendered_widgets(form.fields[name]):
            widget.attrs["data-achievement-types"] = ",".join(types)
            widget.attrs["class"] = (widget.attrs.get("class", "") + " achievement-param").strip()
    if "type" in form.fields:
        form.fields["type"].widget.attrs["data-type-help"] = json.dumps(
            {definition.type.value: definition.help for definition in TYPES.values()}
        )
        form.fields["type"].widget.attrs["data-goal-labels"] = json.dumps(
            {definition.type.value: definition.goal_label for definition in TYPES.values()}
        )


def clean_parameters(form: forms.ModelForm, cleaned_data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate the settings needed by the chosen type, and reset the ones it doesn't use so they can't silently
    filter anything.
    """
    achievement_type = cleaned_data.get("type")
    definition = TYPES.get(achievement_type) if achievement_type else None
    if definition is None:
        return cleaned_data
    for name in PARAMETER_FIELDS:
        if name not in form.fields:
            continue
        model_field = Achievement._meta.get_field(name)
        if name not in definition.fields or (not model_field.null and cleaned_data.get(name) in (None, "")):
            cleaned_data[name] = None if model_field.null else model_field.get_default()
    if achievement_type == AchievementType.COMPLETE_GROUP and not cleaned_data.get("group"):
        form.add_error("group", "A group is required for this type.")
    target = cleaned_data.get("target_value")
    if target is not None and target < 1 and achievement_type != AchievementType.COMPLETE_GROUP:
        form.add_error("target_value", "The goal must be at least 1.")
    return cleaned_data


class AchievementAdminForm(forms.ModelForm):
    class Meta:
        model = Achievement
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configure_parameter_widgets(self)

    def clean(self):
        return clean_parameters(self, super().clean())


class RecomputeForm(AdminActionForm):
    give_rewards = forms.BooleanField(
        required=False, initial=True, help_text="Give the currency reward to the players unlocking an achievement."
    )

    class Meta:
        list_objects = True
        help_text = (
            "Gives every player the progress they already have, and unlocks the achievements they already deserve, "
            "without notifying them. Only works for achievements based on what players own or have: owned "
            "treasures, groups, completion, friends, favorites and playtime."
        )


@admin.register(AchievementCategory)
class AchievementCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "emoji", "position", "achievement_count")
    list_editable = ("emoji", "position")
    search_fields = ("name",)

    def get_queryset(self, request: "HttpRequest") -> "QuerySet[AchievementCategory]":
        return super().get_queryset(request).annotate(achievement_count=Count("achievements"))

    @admin.display(description="Achievements", ordering="achievement_count")
    def achievement_count(self, obj: AchievementCategory) -> int:
        return obj.achievement_count  # type: ignore


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    form = AchievementAdminForm
    save_on_top = True
    save_as = True
    autocomplete_fields = ("ball", "special", "group", "category")
    filter_horizontal = ("prerequisities",)
    readonly_fields = ("thumbnail_large", "goal_preview", "proposed_by", "created_at", "updated_at")
    fieldsets = [
        (
            None,
            {
                "description": 'Tip: use "Save as new" at the bottom to duplicate an achievement, or "Create a series" '
                "in the achievement list to create several levels of the same achievement at once.",
                "fields": ("name", "description", "category", "thumbnail", "thumbnail_large", "hidden", "position"),
            },
        ),
        (
            "Goal",
            {
                "description": "Only the settings used by the selected type are shown.",
                "fields": ("type", "target_value", "goal_preview", *PARAMETER_FIELDS),
            },
        ),
        ("Reward", {"fields": ("currency_reward",)}),
        ("Publication", {"fields": ("status", "notes", "proposed_by", "created_at", "updated_at")}),
        ("Prerequisites", {"classes": ("collapse",), "fields": ("prerequisities", "prerequisite_logic")}),
    ]

    list_display = (
        "thumbnail_small",
        "name",
        "category",
        "type",
        "goal",
        "currency_reward",
        "unlocked_count",
        "status",
        "position",
    )
    list_display_links = ("name",)
    list_editable = ("status", "position")
    list_filter = ("status", "category", "type", "hidden")
    list_select_related = ("ball", "special", "group", "category")
    search_fields = ("name", "description", "notes")
    ordering = ("category__position", "position", "name")
    list_per_page = 100
    actions = ("make_active", "make_draft", "make_retired", "recompute")

    class Media:
        # jQuery is listed first on purpose: the admin would otherwise be free to load the script before
        # jquery.init.js, and `django.jQuery` would not exist yet when it runs
        js = ("admin/js/vendor/jquery/jquery.js", "admin/js/jquery.init.js", "admin/achievement_dynamic_fields.js")

    def get_queryset(self, request: "HttpRequest") -> "QuerySet[Achievement]":
        return (
            super()
            .get_queryset(request)
            .annotate(unlocked_count=Count("userachievement", filter=Q(userachievement__completed=True)))
        )

    def get_urls(self):
        return [
            path(
                "series/",
                self.admin_site.admin_view(self.create_series_view),
                name="achievement_app_achievement_series",
            ),
            *super().get_urls(),
        ]

    def save_model(self, request: "HttpRequest", obj: Achievement, form, change: bool):
        if not change and obj.proposed_by is None and request.user.is_authenticated:
            obj.proposed_by = request.user  # type: ignore
        super().save_model(request, obj, form, change)

    @admin.display(description="")
    def thumbnail_small(self, obj: Achievement):
        if not obj.thumbnail:
            return ""
        return format_html('<img src="/media/{}" height="32" />', obj.thumbnail.name)

    @admin.display(description="Current thumbnail")
    def thumbnail_large(self, obj: Achievement):
        if not obj.thumbnail:
            return "-"
        return format_html('<img src="/media/{}" height="96" />', obj.thumbnail.name)

    @admin.display(description="Goal")
    def goal(self, obj: Achievement) -> str:
        return goal_text(obj)

    @admin.display(description="Goal shown to players")
    def goal_preview(self, obj: Achievement) -> str:
        if not obj.pk:
            return "Save the achievement to see the generated goal."
        return goal_text(obj)

    @admin.display(description="Unlocked by", ordering="unlocked_count")
    def unlocked_count(self, obj: Achievement) -> int:
        return obj.unlocked_count  # type: ignore

    @admin.action(description="Publish the selected achievements (active)")
    def make_active(self, request: "HttpRequest", queryset: "QuerySet[Achievement]"):
        updated = queryset.update(status=Achievement.Status.ACTIVE)
        self.message_user(request, f"{updated} achievement(s) are now active.", messages.SUCCESS)

    @admin.action(description="Move the selected achievements back to drafts")
    def make_draft(self, request: "HttpRequest", queryset: "QuerySet[Achievement]"):
        updated = queryset.update(status=Achievement.Status.DRAFT)
        self.message_user(request, f"{updated} achievement(s) are now drafts.", messages.SUCCESS)

    @admin.action(description="Retire the selected achievements")
    def make_retired(self, request: "HttpRequest", queryset: "QuerySet[Achievement]"):
        updated = queryset.update(status=Achievement.Status.RETIRED)
        self.message_user(request, f"{updated} achievement(s) are now retired.", messages.SUCCESS)

    @action_with_form(RecomputeForm, description="Recompute the progress of every player")
    def recompute(self, request: "HttpRequest", queryset: "QuerySet[Achievement]", data: dict):
        for achievement in queryset:
            if achievement.type not in RECOMPUTABLE_TYPES:
                self.message_user(
                    request,
                    f"{achievement.name}: skipped, progress counting actions can't be recomputed.",
                    messages.WARNING,
                )
                continue
            updated, unlocked = recompute_progress(achievement, give_rewards=data["give_rewards"])
            self.message_user(
                request,
                f"{achievement.name}: progress updated for {updated} player(s), {unlocked} unlocked it.",
                messages.SUCCESS,
            )

    def create_series_view(self, request: "HttpRequest"):
        form_class = achievement_series_form(self.admin_site)
        form = form_class(request.POST or None)
        if request.method == "POST" and form.is_valid():
            created = form.save_series(request)
            self.message_user(request, f"{len(created)} achievement(s) created.", messages.SUCCESS)
            return redirect(reverse("admin:achievement_app_achievement_changelist"))
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Create a series of achievements",
            "form": form,
            "media": self.media + form.media,
        }
        return TemplateResponse(request, "admin/achievement_app/achievement/series.html", context)


def achievement_series_form(admin_site: admin.AdminSite) -> type[forms.ModelForm]:
    def autocomplete(field_name: str):
        return AutocompleteSelect(Achievement._meta.get_field(field_name), admin_site)

    class AchievementSeriesForm(forms.ModelForm):
        levels = forms.CharField(
            widget=forms.Textarea(attrs={"rows": 8, "cols": 90}),
            help_text="One achievement per line: <b>name | goal | reward | description</b>. The reward and the "
            "description are optional.<br>Example:<br>Trading novice | 1 | 1500<br>Trading expert | 200 | 5000 | "
            "Complete 200 trades.",
        )

        class Meta:
            model = Achievement
            fields = ("type", *PARAMETER_FIELDS, "category", "status", "hidden")
            widgets = {name: autocomplete(name) for name in ("ball", "special", "group", "category")}

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            configure_parameter_widgets(self)
            self.parsed_levels: list[tuple[str, int, int, str]] = []

        def clean_levels(self):
            levels = []
            names = set()
            for number, line in enumerate(self.cleaned_data["levels"].splitlines(), start=1):
                if not line.strip():
                    continue
                parts = [part.strip() for part in line.split("|")]
                if len(parts) < 2:
                    raise forms.ValidationError(f"Line {number}: expected at least a name and a goal.")
                name, goal, reward, description = (parts + ["", ""])[:4]
                try:
                    goal_value, reward_value = int(goal), int(reward or 0)
                except ValueError:
                    raise forms.ValidationError(f"Line {number}: the goal and the reward must be whole numbers.")
                if goal_value < 0 or reward_value < 0:
                    raise forms.ValidationError(f"Line {number}: the goal and the reward can't be negative.")
                if name in names or Achievement.objects.filter(name=name).exists():
                    raise forms.ValidationError(f'Line {number}: an achievement named "{name}" already exists.')
                names.add(name)
                levels.append((name, goal_value, reward_value, description))
            if not levels:
                raise forms.ValidationError("Add at least one achievement.")
            self.parsed_levels = levels
            return self.cleaned_data["levels"]

        def clean(self):
            # the goals are checked line by line in clean_levels
            return clean_parameters(self, super().clean())

        def save_series(self, request: "HttpRequest") -> list[Achievement]:
            base_position = (
                Achievement.objects.filter(category=self.cleaned_data.get("category"))
                .order_by("-position")
                .values_list("position", flat=True)
                .first()
                or 0
            )
            created = []
            with transaction.atomic():
                for index, (name, goal, reward, description) in enumerate(self.parsed_levels, start=1):
                    achievement = Achievement(
                        name=name,
                        description=description or None,
                        target_value=goal,
                        currency_reward=reward,
                        position=base_position + index,
                        proposed_by=request.user if request.user.is_authenticated else None,
                    )
                    for field in self._meta.fields:
                        setattr(achievement, field, self.cleaned_data.get(field))
                    achievement.save()
                    created.append(achievement)
            return created

    return AchievementSeriesForm


@admin.register(UserAchievement)
class UserAchievementAdmin(admin.ModelAdmin):
    list_display = ("achievement", "player", "progress", "completed", "completed_at")
    list_filter = ("completed", "achievement__category", "achievement")
    list_select_related = ("achievement", "player")
    search_fields = ("player__discord_id", "achievement__name")
    search_help_text = "Search by player Discord ID or achievement name"
    autocomplete_fields = ("player", "achievement")
    show_full_result_count = False


@admin.register(PlayerAchievementStats)
class PlayerAchievementStatsAdmin(admin.ModelAdmin):
    list_display = ("player", "first_catch_at")
    search_fields = ("player__discord_id",)
    autocomplete_fields = ("player",)
