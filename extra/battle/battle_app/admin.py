from django.contrib import admin

from .models import Buff


# Register your models here.
@admin.register(Buff)
class BuffAdmin(admin.ModelAdmin):
    pass
