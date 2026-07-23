from django import forms
from django.contrib import admin

from .models import ACHIEVEMENT_TYPE_SCHEMA, Achievement

EXTRA_PARAM_FIELDS = {
    "server_id": forms.CharField(required=False, label="Server ID", help_text="This's for Catch Ball achievement-type"),
    "max_seconds": forms.IntegerField(
        required=False, label="Max seconds to Catch", help_text="This's for Fastest Catcher achievement-type."
    ),
    "requires_currency": forms.BooleanField(
        required=False, label="Requires Currency", help_text="This's for Complete Trade achievement-type"
    ),
    "user_id": forms.CharField(required=False, label="User ID", help_text="This's for Receive Ball achievement-type"),
    "hex_contains": forms.CharField(
        required=False, label="Hex ID Contains", help_text="This's for Catch Ball achievement-type"
    ),
    "attack_bonus": forms.IntegerField(
        required=False, label="Attack Bonus", help_text="This's for Catch Ball achievement-type"
    ),
    "health_bonus": forms.IntegerField(
        required=False, label="Health Bonus", help_text="This's for Catch Ball achievement-type"
    ),
    "unit": forms.ChoiceField(
        required=False,
        label="Unit",
        choices=[("days", "Days"), ("months", "Months"), ("years", "Years")],
        help_text="This's for Playtime achievement-type. To set a value, use target value",
    ),
}


class AchievementAdminForm(forms.ModelForm):
    server_id = forms.CharField(required=False, label="Server ID", help_text="This's for Catch Ball achievement-type")
    max_seconds = forms.IntegerField(
        required=False, label="Max seconds to Catch", help_text="This's for Fastest Catcher achievement-type."
    )
    requires_currency = forms.BooleanField(
        required=False, label="Requires Currency", help_text="This's for Complete Trade achievement-type"
    )
    user_id = forms.CharField(required=False, label="User ID", help_text="This's for Receive Ball achievement-type")
    hex_contains = forms.CharField(
        required=False, label="Hex ID Contains", help_text="This's for Catch Ball achievement-type"
    )
    attack_bonus = forms.IntegerField(
        required=False, label="Attack Bonus", help_text="This's for Catch Ball achievement-type"
    )
    health_bonus = forms.IntegerField(
        required=False, label="Health Bonus", help_text="This's for Catch Ball achievement-type"
    )
    unit = forms.ChoiceField(
        required=False,
        label="Unit",
        choices=[("days", "Days"), ("months", "Months"), ("years", "Years")],
        help_text="This's for Playtime achievement-type. To set a value, use target value",
    )

    class Meta:
        model = Achievement
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name in EXTRA_PARAM_FIELDS.keys():
            if self.instance and self.instance.extra_params:
                self.fields[name].initial = self.instance.extra_params.get(name)

            relevant_types = [
                t.value for t, fields in ACHIEVEMENT_TYPE_SCHEMA.items() if any(f["name"] == name for f in fields)
            ]
            self.fields[name].widget.attrs["data-achievement-types"] = ",".join(relevant_types)
            self.fields[name].widget.attrs["class"] = "extra-param-field"

    def save(self, commit=True):
        instance = super().save(commit=False)
        achievement_type = self.cleaned_data["type"]
        relevant_fields = [f["name"] for f in ACHIEVEMENT_TYPE_SCHEMA.get(achievement_type, [])]
        instance.extra_params = {
            name: self.cleaned_data[name] for name in relevant_fields if self.cleaned_data.get(name) not in (None, "")
        }
        if commit:
            instance.save()
        return instance


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    form = AchievementAdminForm
    exclude = ("extra_params",)
    list_display = ("name", "type")
    list_filter = ("type",)
    filter_horizontal = ("prerequisities",)

    class Media:
        js = ("admin/achievement_dynamic_fields.js",)

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        extra_fields = list(EXTRA_PARAM_FIELDS.keys())
        return fields + [f for f in extra_fields if f not in fields]
