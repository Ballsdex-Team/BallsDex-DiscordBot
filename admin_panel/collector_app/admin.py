from typing import TYPE_CHECKING

from admin_auto_filters.filters import AutocompleteFilter
from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django_admin_action_forms import AdminActionForm, action_with_form

from bd_models.utils import ApproxCountPaginator

from .models import (
    Collector,
    CollectorInstance,
    CollectorRequirement,
    CollectorSettings,
    CollectorTier,
    CollectorTierLevel,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest


@admin.register(CollectorSettings)
class CollectorSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request: "HttpRequest") -> bool:
        return super().has_add_permission(request) and CollectorSettings.objects.first() is None

    def has_delete_permission(self, request: "HttpRequest", obj: CollectorSettings | None = None) -> bool:
        return False


@admin.register(CollectorTierLevel)
class CollectorTierLevelAdmin(admin.ModelAdmin):
    list_display = ("name", "position", "emoji", "special", "claimable", "monitored", "collector_count")
    list_editable = ("position", "claimable", "monitored")
    autocomplete_fields = ("special",)
    search_fields = ("name",)

    def get_queryset(self, request: "HttpRequest") -> "QuerySet[CollectorTierLevel]":
        return super().get_queryset(request).annotate(collector_count=Count("collector_tiers"))

    @admin.display(description="Collectors", ordering="collector_count")
    def collector_count(self, obj: CollectorTierLevel) -> int:
        return obj.collector_count  # type: ignore

    def has_delete_permission(self, request: "HttpRequest", obj: CollectorTierLevel | None = None) -> bool:
        # a tier used by collectors or claimed cards is protected in the database anyway
        return super().has_delete_permission(request, obj)


class TiersInline(admin.TabularInline):
    model = CollectorTier
    extra = 0
    autocomplete_fields = ("special",)
    fields = ("level", "enabled", "special", "no_special", "tradeable", "price")
    verbose_name_plural = "Tiers (players pick one of these after selecting the collector)"


class RequirementsInline(admin.TabularInline):
    model = CollectorRequirement
    extra = 0
    autocomplete_fields = ("ball", "special")
    fields = ("level", "ball", "special", "amount", "delete_balls")
    ordering = ("level__position", "amount")
    verbose_name_plural = "Requirements (each one belongs to a tier)"


class BallFilter(AutocompleteFilter):
    title = "countryball"
    field_name = "ball"


class AddTierForm(AdminActionForm):
    level = forms.ModelChoiceField(queryset=CollectorTierLevel.objects.all(), help_text="The tier to add.")
    copy_requirements_from = forms.ModelChoiceField(
        queryset=CollectorTierLevel.objects.all(),
        required=False,
        help_text="Copy the requirements of this tier into the new one. Leave empty to add the tier without "
        "requirements.",
    )
    multiplier = forms.IntegerField(
        min_value=1, initial=2, help_text="The amount of every copied requirement is multiplied by this number."
    )
    tradeable = forms.BooleanField(required=False, initial=True, help_text="Whether the claimed cards can be traded.")

    class Meta:
        list_objects = True
        help_text = (
            "The tier is added to every selected collector that doesn't have it yet. Collectors that already have "
            "it are left untouched."
        )


@admin.register(Collector)
class CollectorAdmin(admin.ModelAdmin):
    save_on_top = True
    autocomplete_fields = ("ball",)
    inlines = (TiersInline, RequirementsInline)
    fieldsets = [(None, {"fields": ("name", "ball")}), ("Time Range", {"fields": ("start_date", "end_date")})]

    list_display = ("name", "ball", "tier_summary", "pk")
    list_filter = (BallFilter, "tiers__level", "created_at")
    search_fields = ("name", "ball__country")
    ordering = ["-created_at"]
    actions = ("add_tier",)
    show_facets = admin.ShowFacets.NEVER  # type: ignore  # hide filtered counts (considerable slowdown)
    show_full_result_count = False
    paginator = ApproxCountPaginator

    def get_queryset(self, request: "HttpRequest") -> "QuerySet[Collector]":
        tiers = CollectorTier.objects.select_related("level").order_by("level__position")
        return super().get_queryset(request).select_related("ball").prefetch_related(Prefetch("tiers", tiers))

    @admin.display(description="Tiers")
    def tier_summary(self, obj: Collector):
        return format_html_join(
            " ",
            '<span title="{}" style="opacity: {}">{}</span>',
            (
                (
                    "enabled" if tier.enabled and tier.level.claimable else "disabled",
                    1 if tier.enabled and tier.level.claimable else 0.4,
                    tier.level.name,
                )
                for tier in obj.tiers.all()
            ),
        ) or format_html("<em>{}</em>", "no tier")

    @action_with_form(AddTierForm, description="Add a tier to the selected collectors")
    def add_tier(self, request: "HttpRequest", queryset: "QuerySet[Collector]", data: dict):
        level: CollectorTierLevel = data["level"]
        source: CollectorTierLevel | None = data["copy_requirements_from"]
        multiplier: int = data["multiplier"]
        if source is not None and source.pk == level.pk:
            self.message_user(request, "You can't copy the requirements of the tier you're adding.", messages.ERROR)
            return

        added = skipped = copied = 0
        with transaction.atomic():
            for collector in queryset:
                if CollectorTier.objects.filter(collector=collector, level=level).exists():
                    skipped += 1
                    continue
                CollectorTier.objects.create(collector=collector, level=level, tradeable=data["tradeable"])
                added += 1
                if source is None:
                    continue
                requirements = [
                    CollectorRequirement(
                        collector=collector,
                        level=level,
                        ball_id=requirement.ball_id,
                        special_id=requirement.special_id,
                        amount=requirement.amount * multiplier,
                        delete_balls=requirement.delete_balls,
                    )
                    for requirement in CollectorRequirement.objects.filter(collector=collector, level=source)
                ]
                CollectorRequirement.objects.bulk_create(requirements)
                copied += len(requirements)

        self.message_user(
            request,
            f"{level.name} added to {added} collector(s) with {copied} requirement(s) copied. "
            f"{skipped} collector(s) already had it.",
            messages.SUCCESS,
        )


class CollectorInstanceStatusFilter(admin.SimpleListFilter):
    title = "status"
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return (
            ("safe", "Monitored and safe"),
            ("at_risk", "At risk (timer running)"),
            ("revoked", "Taken back"),
            ("legacy", "Not monitored"),
        )

    def queryset(self, request, queryset):
        match self.value():
            case "safe":
                return queryset.filter(monitored=True, revoked_at__isnull=True, at_risk_since__isnull=True)
            case "at_risk":
                return queryset.filter(revoked_at__isnull=True, at_risk_since__isnull=False)
            case "revoked":
                return queryset.filter(revoked_at__isnull=False)
            case "legacy":
                return queryset.filter(monitored=False, revoked_at__isnull=True)
        return queryset


@admin.register(CollectorInstance)
class CollectorInstanceAdmin(admin.ModelAdmin):
    list_display = ("collector", "level", "player", "status", "claimed_at", "grace_ends_at")
    list_filter = (CollectorInstanceStatusFilter, "level", "claimed_at")
    list_select_related = ("collector", "level", "player")
    search_fields = ("collector__name", "player__discord_id")
    search_help_text = "Search by collector name or player Discord ID"
    autocomplete_fields = ("player", "collector", "ball_instance")
    readonly_fields = ("claimed_at", "at_risk_since", "grace_ends_at", "revoked_at")
    actions = ("stop_monitoring",)
    show_full_result_count = False
    paginator = ApproxCountPaginator

    @admin.display(description="Status")
    def status(self, obj: CollectorInstance):
        if obj.revoked_at:
            return format_html('<span style="color: crimson">{}</span>', "Taken back")
        if obj.at_risk_since:
            return format_html('<span style="color: orange">{}</span>', "At risk")
        if obj.monitored:
            return format_html('<span style="color: green">{}</span>', "Safe")
        return "Not monitored"

    @admin.action(description="Stop monitoring the selected cards (they can't be taken back anymore)")
    def stop_monitoring(self, request: "HttpRequest", queryset: "QuerySet[CollectorInstance]"):
        updated = queryset.filter(Q(monitored=True) | Q(at_risk_since__isnull=False), revoked_at__isnull=True).update(
            monitored=False, at_risk_since=None, grace_ends_at=None
        )
        self.message_user(request, f"{updated} card(s) are not monitored anymore.", messages.SUCCESS)

    def save_model(self, request, obj: CollectorInstance, form, change):
        if not change and obj.claimed_at is None:
            obj.claimed_at = timezone.now()
        super().save_model(request, obj, form, change)
