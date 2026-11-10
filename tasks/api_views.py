from django.db.models import QuerySet
from django.utils import timezone
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from tasks.api_serializers import TaskSerializer
from tasks.models import Task


class TaskViewSet(viewsets.ModelViewSet):

    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title"]
    ordering_fields = ["scheduled_for", "created_at", "status"]

    def get_queryset(self) -> QuerySet:
        queryset = Task.objects.filter(owner=self.request.user)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    def perform_create(self, serializer):
        values = {"owner": self.request.user}
        if serializer.validated_data.get("status") == Task.Status.DONE:
            values["completed_at"] = timezone.now()
        serializer.save(**values)

    def perform_update(self, serializer):
        obj = serializer.instance
        changes = serializer.validated_data
        reminder_fields = {"scheduled_for", "remind_enabled", "remind_minutes_before"}
        reminder_changed = any(
            field in changes and changes[field] != getattr(obj, field)
            for field in reminder_fields
        )
        new_status = changes.get("status", obj.status)
        values = {}
        if reminder_changed or (obj.status == Task.Status.DONE and new_status != obj.status):
            values["reminder_sent_at"] = None
        if new_status == Task.Status.DONE:
            if obj.status != Task.Status.DONE or obj.completed_at is None:
                values["completed_at"] = timezone.now()
        elif obj.completed_at is not None:
            values["completed_at"] = None
        serializer.save(**values)

    @action(detail=True, methods=["post"], url_path="concluir")
    def concluir(self, request, pk=None):
        task = self.get_object()
        task.mark_complete()
        return Response(self.get_serializer(task).data, status=status.HTTP_200_OK)
