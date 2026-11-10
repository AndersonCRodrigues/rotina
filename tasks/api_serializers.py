from rest_framework import serializers

from tasks.models import Task


class TaskSerializer(serializers.ModelSerializer):

    is_overdue = serializers.BooleanField(read_only=True)
    remind_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Task
        fields = [
            "id",
            "title",
            "notes",
            "status",
            "scheduled_for",
            "remind_enabled",
            "remind_minutes_before",
            "completed_at",
            "remind_at",
            "is_overdue",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "completed_at", "created_at", "updated_at"]

    def validate(self, attrs):
        enabled = attrs.get(
            "remind_enabled", getattr(self.instance, "remind_enabled", False)
        )
        offset = attrs.get(
            "remind_minutes_before",
            getattr(self.instance, "remind_minutes_before", None),
        )
        if enabled and not offset:
            raise serializers.ValidationError({
                "remind_minutes_before": (
                    "Escolha com quanto tempo de antecedência avisar."
                )
            })
        if attrs.get("remind_enabled", getattr(self.instance, "remind_enabled", False)) is False:
            attrs["remind_minutes_before"] = None
        return attrs
