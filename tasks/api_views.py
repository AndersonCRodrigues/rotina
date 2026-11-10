from django.db.models import QuerySet
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
        serializer.save(owner=self.request.user)

    def perform_update(self, serializer):
        obj = serializer.instance
        remind_fields = {"scheduled_for", "remind_enabled", "remind_minutes_before"}
        changed = any(
            key in serializer.validated_data and serializer.validated_data[key] != getattr(obj, key)
            for key in remind_fields
        )
        serializer.save(reminder_sent_at=None) if changed else serializer.save()

    @action(detail=True, methods=["post"], url_path="concluir")
    def concluir(self, request, pk=None):
        task = self.get_object()
        task.mark_complete()
        return Response(self.get_serializer(task).data, status=status.HTTP_200_OK)
