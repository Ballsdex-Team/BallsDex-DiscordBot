from django import forms
from django_admin_action_forms import AdminActionForm


class BlacklistActionForm(AdminActionForm):
    reason = forms.CharField(label="Reason", required=True)
