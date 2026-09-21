"""
The event pass builder: one page to lay out a pass, its tiers, its quests and their rewards.

Two things this admin does on purpose:

- only the settings the selected quest type actually uses are shown (the rest are reset when saving), so a filter
  can never silently narrow a quest it doesn't belong to;
- a quest whose package isn't installed says so, loudly, instead of quietly never progressing.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Q
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .integrations import INTEGRATIONS, check_integrations
from .models import (
    EventPass,
    Measure,
    PassTier,
    PlayerPass,
    PlayerQuest,
    Quest,
    QuestType,
    Reward,
    RewardGrant,
    RewardLine,
    TierRequirement,
)
from .types import PARAMETER_FIELDS, TYPES, goal_text

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest

# the settings that decide *what* counts sit in the Goal section; the ones that only narrow it down further are
# folded away, so a simple "catch a treasure" quest is a handful of rows and not a wall of them
FINE_FILTERS = (
    "min_rarity",
    "max_rarity",
    "min_attack_bonus",
    "min_health_bonus",
    "hex_contains",
    "max_catch_seconds",
    "in_one_trade",
)
MAIN_FILTERS = tuple(name for name in PARAMETER_FIELDS if name not in FINE_FILTERS)


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
    Tag every setting with the quest types using it: the admin script only shows the relevant ones.
    """
    for name in PARAMETER_FIELDS:
        if name not in form.fields:
            continue
        # hidden settings may not be submitted, they fall back to their default value when cleaned
        form.fields[name].required = False
        types = [definition.type.value for definition in TYPES.values() if name in definition.fields]
        for widget in rendered_widgets(form.fields[name]):
            widget.attrs["data-quest-types"] = ",".join(types)
            widget.attrs["class"] = (widget.attrs.get("class", "") + " eventpass-param").strip()
    if "type" in form.fields:
        form.fields["type"].widget.attrs["data-type-help"] = json.dumps(
            {
                definition.type.value: definition.help
                + (
                    ""
                    if definition.integration is None or definition.integration.installed
                    else f" ⚠ The {definition.integration.label} package is NOT installed: "
                    "this quest would never progress."
                )
                for definition in TYPES.values()
            }
        )
        form.fields["type"].widget.attrs["data-goal-labels"] = json.dumps(
            {definition.type.value: definition.goal_label for definition in TYPES.values()}
        )
        form.fields["type"].widget.attrs["data-measures"] = json.dumps(
            {definition.type.value: [measure.value for measure in definition.measures] for definition in TYPES.values()}
        )


def clean_parameters(form: forms.ModelForm, cleaned_data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate the settings the chosen type needs, and reset the ones it doesn't use.
    """
    quest_type = cleaned_data.get("type")
    definition = TYPES.get(quest_type) if quest_type else None
    if definition is None:
        return cleaned_data
    for name in PARAMETER_FIELDS:
        if name not in form.fields:
            continue
        model_field = Quest._meta.get_field(name)
        if name not in definition.fields or (not model_field.null and cleaned_data.get(name) in (None, "")):
            cleaned_data[name] = None if model_field.null else model_field.get_default()
    if quest_type == QuestType.COMMAND and not cleaned_data.get("command_name"):
        form.add_error("command_name", "Give the name of the command to count.")
    measure = cleaned_data.get("measure")
    if measure and Measure(measure) not in definition.measures:
        cleaned_data["measure"] = definition.measures[0]
    return cleaned_data


class QuestAdminForm(forms.ModelForm):
    # changing any of these on a live quest would break the progress players already made on it
    LOCKED_WHEN_LIVE = ("event_pass", "type", "target", "measure", "reset")

    class Meta:
        model = Quest
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configure_parameter_widgets(self)

    def clean(self):
        cleaned_data = clean_parameters(self, super().clean())
        return self.check_locked(cleaned_data)

    def check_locked(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        """
        Refuse the changes a live pass can't take. The fields stay editable on screen (the form would lose the type
        dropdown the settings depend on), the change is simply rejected with the reason.
        """
        instance = self.instance
        if not instance.pk or not instance.event_pass_id:
            return cleaned_data
        if instance.event_pass.status != EventPass.Status.ACTIVE:
            return cleaned_data
        for name in self.LOCKED_WHEN_LIVE:
            if name not in self.fields or name not in cleaned_data:
                continue
            value = cleaned_data[name]
            if (value.pk if hasattr(value, "pk") else value) == self.initial.get(name):
                continue
            self.add_error(
                name,
                "This pass is live: changing it would break the progress players already made on this quest. "
                "Move the pass back to draft first, or make a new quest.",
            )
        return cleaned_data


class RewardLineInline(admin.TabularInline):
    model = RewardLine
    extra = 1
    autocomplete_fields = ("ball", "special")
    fields = (
        "position",
        "kind",
        "amount",
        "ball",
        "quantity",
        "special",
        "frame_key",
        "bonus_mode",
        "attack_bonus",
        "health_bonus",
        "tradeable",
    )


@admin.register(Reward)
class RewardAdmin(admin.ModelAdmin):
    inlines = (RewardLineInline,)
    list_display = ("name", "emoji", "content", "used_by")
    search_fields = ("name", "message")
    save_as = True

    @admin.display(description="Contains")
    def content(self, obj: Reward) -> str:
        return " + ".join(str(line) for line in obj.lines.all()) or "-"

    @admin.display(description="Used by")
    def used_by(self, obj: Reward) -> str:
        names = [quest.name for quest in obj.quests.all()[:5]]
        return ", ".join(names) or "-"


class TierRequirementInline(admin.StackedInline):
    model = TierRequirement
    extra = 1
    autocomplete_fields = ("ball", "special")
    filter_horizontal = ("quests",)
    fields = ("kind", "count", "quests", "ball", "special", "date")
    verbose_name = "unlock requirement"
    verbose_name_plural = "unlock requirements"


class PassTierInline(admin.TabularInline):
    model = PassTier
    extra = 0
    show_change_link = True
    fields = ("position", "name", "emoji", "unlock_logic", "reward", "quest_count")
    readonly_fields = ("quest_count",)
    autocomplete_fields = ("reward",)
    ordering = ("position",)

    @admin.display(description="Quests")
    def quest_count(self, obj: PassTier) -> str:
        if not obj.pk:
            return "-"
        return str(obj.quests.count())


class QuestInline(admin.TabularInline):
    """
    A read-only overview: quests have too many settings to edit them from here, they each have their own page.
    """

    model = Quest
    extra = 0
    show_change_link = True
    can_delete = False
    fields = ("position", "name", "tier", "mandatory", "type", "goal", "reward", "completed_by")
    readonly_fields = fields
    ordering = ("tier__position", "position")

    def has_add_permission(self, request: HttpRequest, obj) -> bool:
        return False

    @admin.display(description="Goal")
    def goal(self, obj: Quest) -> str:
        return goal_text(obj)

    @admin.display(description="Completed by")
    def completed_by(self, obj: Quest) -> int:
        return obj.progress.filter(completed_at__isnull=False).count()


@admin.register(EventPass)
class EventPassAdmin(admin.ModelAdmin):
    save_on_top = True
    save_as = True
    inlines = (PassTierInline, QuestInline)
    autocomplete_fields = ("final_reward",)
    readonly_fields = ("integration_status", "created_by", "created_at", "updated_at")
    fieldsets = [
        (None, {"fields": ("name", "emoji", "description", "banner", "colour", "position")}),
        (
            "When",
            {
                "description": "Quests only progress between these dates. Claiming can stay open a little longer.",
                "fields": ("starts_at", "ends_at", "claim_until"),
            },
        ),
        ("Where", {"fields": ("main_server_only", "main_server_id")}),
        ("End of the pass", {"fields": ("final_reward", "final_message")}),
        (
            "Publication",
            {"fields": ("status", "integration_status", "notes", "created_by", "created_at", "updated_at")},
        ),
    ]
    list_display = ("name", "status", "starts_at", "ends_at", "tier_count", "quest_count", "player_count")
    list_filter = ("status",)
    search_fields = ("name", "description", "notes")

    def get_queryset(self, request: HttpRequest) -> QuerySet[EventPass]:
        return (
            super()
            .get_queryset(request)
            .annotate(
                tiers_count=Count("tiers", distinct=True),
                quests_count=Count("quests", distinct=True),
                players_count=Count("players", distinct=True),
            )
        )

    def save_model(self, request: HttpRequest, obj: EventPass, form, change: bool):
        if not change and obj.created_by is None and request.user.is_authenticated:
            obj.created_by = request.user  # type: ignore
        super().save_model(request, obj, form, change)
        for warning in check_integrations({quest.type for quest in obj.quests.all()}):
            self.message_user(request, warning, messages.WARNING)

    @admin.display(description="Tiers", ordering="tiers_count")
    def tier_count(self, obj: EventPass) -> int:
        return obj.tiers_count  # type: ignore

    @admin.display(description="Quests", ordering="quests_count")
    def quest_count(self, obj: EventPass) -> int:
        return obj.quests_count  # type: ignore

    @admin.display(description="Players", ordering="players_count")
    def player_count(self, obj: EventPass) -> int:
        return obj.players_count  # type: ignore

    @admin.display(description="Packages needed by the quests")
    def integration_status(self, obj: EventPass) -> str:
        rows = []
        for integration in INTEGRATIONS:
            mark = "✅" if integration.installed else "❌"
            rows.append(f"<li>{mark} {integration.label} — {integration.note}</li>")
        warnings = check_integrations({quest.type for quest in obj.quests.all()} if obj.pk else None)
        alert = "".join(f'<p style="color:#b32d2e"><strong>{warning}</strong></p>' for warning in warnings)
        return mark_safe(f"{alert}<ul>{''.join(rows)}</ul>")  # noqa: S308


@admin.register(PassTier)
class PassTierAdmin(admin.ModelAdmin):
    inlines = (TierRequirementInline,)
    autocomplete_fields = ("event_pass", "reward")
    list_display = ("name", "event_pass", "position", "requirement_count", "quest_count", "reward")
    list_filter = ("event_pass",)
    list_editable = ("position",)
    search_fields = ("name",)
    ordering = ("event_pass__position", "position")
    fields = ("event_pass", "name", "emoji", "description", "position", "unlock_logic", "locked_message", "reward")

    @admin.display(description="Requirements")
    def requirement_count(self, obj: PassTier) -> int:
        return obj.requirements.count()

    @admin.display(description="Quests")
    def quest_count(self, obj: PassTier) -> int:
        return obj.quests.count()


@admin.register(Quest)
class QuestAdmin(admin.ModelAdmin):
    form = QuestAdminForm
    save_on_top = True
    save_as = True
    autocomplete_fields = (
        "event_pass",
        "tier",
        "reward",
        "ball",
        "special",
        "group",
        "item",
        "merchant_item",
        "collector",
    )
    readonly_fields = ("goal_preview", "thumbnail_large", "stats")
    fieldsets = [
        (
            None,
            {
                "description": 'Tip: "Save as new" at the bottom duplicates a quest, which is the fastest way to '
                "build a tier.",
                "fields": (
                    "event_pass",
                    "tier",
                    "mandatory",
                    "name",
                    "description",
                    "emoji",
                    "thumbnail",
                    "thumbnail_large",
                ),
            },
        ),
        (
            "Goal",
            {
                "description": "Only the settings used by the selected type are shown. The others are ignored.",
                "fields": ("type", "target", "measure", "goal_preview", *MAIN_FILTERS),
            },
        ),
        (
            "Fine tuning",
            {
                "classes": ("collapse",),
                "description": "Rarely needed, and hidden altogether when the selected type ignores them.",
                "fields": FINE_FILTERS,
            },
        ),
        ("Reward", {"fields": ("reward", "claim_required", "announce", "completion_message")}),
        (
            "Availability",
            {"fields": ("enabled", "hidden", "position", "reset", "starts_at", "ends_at", "notes", "stats")},
        ),
    ]
    list_display = (
        "name",
        "event_pass",
        "tier",
        "type",
        "goal",
        "reward",
        "completed_by",
        "mandatory",
        "enabled",
        "position",
    )
    list_display_links = ("name",)
    list_editable = ("mandatory", "enabled", "position")
    list_filter = ("event_pass", "tier", "type", "mandatory", "enabled", "hidden", "reset")
    list_select_related = ("event_pass", "tier", "reward")
    search_fields = ("name", "description", "notes")
    list_per_page = 100
    actions = ("enable", "disable")

    class Media:
        # jQuery is listed first on purpose: the admin would otherwise be free to load the script before
        # jquery.init.js, and `django.jQuery` would not exist yet when it runs
        js = ("admin/js/vendor/jquery/jquery.js", "admin/js/jquery.init.js", "admin/eventpass_dynamic_fields.js")

    def get_queryset(self, request: HttpRequest) -> QuerySet[Quest]:
        return (
            super()
            .get_queryset(request)
            .annotate(completed_count=Count("progress", filter=Q(progress__completed_at__isnull=False)))
        )

    def save_model(self, request: HttpRequest, obj: Quest, form, change: bool):
        super().save_model(request, obj, form, change)
        definition = TYPES.get(obj.type)
        if definition and definition.integration and not definition.integration.installed:
            self.message_user(
                request,
                f"The {definition.integration.label} package is not installed: this quest will never progress "
                "until it is.",
                messages.WARNING,
            )

    @admin.display(description="Current thumbnail")
    def thumbnail_large(self, obj: Quest):
        if not obj.thumbnail:
            return "-"
        return format_html('<img src="/media/{}" height="96" />', obj.thumbnail.name)

    @admin.display(description="Goal")
    def goal(self, obj: Quest) -> str:
        return goal_text(obj)

    @admin.display(description="Goal shown to players")
    def goal_preview(self, obj: Quest) -> str:
        if not obj.pk:
            return "Save the quest to see the generated goal."
        return goal_text(obj)

    @admin.display(description="Completed by", ordering="completed_count")
    def completed_by(self, obj: Quest) -> int:
        return getattr(obj, "completed_count", 0)

    @admin.display(description="Players")
    def stats(self, obj: Quest) -> str:
        if not obj.pk:
            return "-"
        started = obj.progress.count()
        completed = obj.progress.filter(completed_at__isnull=False).count()
        claimed = obj.progress.filter(claimed_at__isnull=False).count()
        return f"{started} started · {completed} completed · {claimed} claimed"

    @admin.action(description="Enable the selected quests")
    def enable(self, request: HttpRequest, queryset: QuerySet[Quest]):
        updated = queryset.update(enabled=True)
        self.message_user(request, f"{updated} quest(s) enabled.", messages.SUCCESS)

    @admin.action(description="Disable the selected quests")
    def disable(self, request: HttpRequest, queryset: QuerySet[Quest]):
        updated = queryset.update(enabled=False)
        self.message_user(request, f"{updated} quest(s) disabled.", messages.SUCCESS)


@admin.register(PlayerQuest)
class PlayerQuestAdmin(admin.ModelAdmin):
    list_display = ("player", "quest", "period", "progress", "completed_at", "claimed_at")
    list_filter = ("quest__event_pass", "quest", "period")
    list_select_related = ("player", "quest")
    search_fields = ("player__discord_id",)
    autocomplete_fields = ("player", "quest")
    readonly_fields = ("completed_at", "claimed_at")


@admin.register(PlayerPass)
class PlayerPassAdmin(admin.ModelAdmin):
    list_display = ("player", "event_pass", "joined_at", "final_claimed_at")
    list_filter = ("event_pass",)
    list_select_related = ("player", "event_pass")
    search_fields = ("player__discord_id",)
    autocomplete_fields = ("player",)


@admin.register(RewardGrant)
class RewardGrantAdmin(admin.ModelAdmin):
    list_display = ("player", "event_pass", "source", "source_id", "period", "summary", "granted_at")
    list_filter = ("event_pass", "source")
    list_select_related = ("player", "event_pass", "reward")
    search_fields = ("player__discord_id", "summary")
    readonly_fields = tuple(
        field.name
        for field in RewardGrant._meta.fields  # a grant is a record of what was given, never edited
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False
