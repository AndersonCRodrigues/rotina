from django.contrib import admin

from tasks.models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "status", "scheduled_for", "remind_enabled", "remind_minutes_before")
    list_filter = ("status", "remind_enabled")
    search_fields = ("title", "owner__username")
    date_hierarchy = "scheduled_for"
