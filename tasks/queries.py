from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from tasks.models import Task


def task_summary(tasks):
    now = timezone.now()
    pending = ~Q(status=Task.Status.DONE)
    return tasks.aggregate(
        total=Count("pk"),
        done=Count("pk", filter=Q(status=Task.Status.DONE)),
        overdue=Count("pk", filter=pending & Q(scheduled_for__lt=now)),
        upcoming=Count("pk", filter=pending & Q(scheduled_for__gte=now)),
    )


def calendar_events(user, task_route):
    tasks = Task.objects.filter(owner=user).values("id", "title", "scheduled_for", "status")
    colors = {
        Task.Status.TODO: "#6c757d",
        Task.Status.IN_PROGRESS: "#0d6efd",
        Task.Status.DONE: "#198754",
    }
    return [
        {
            "id": task["id"],
            "title": task["title"],
            "start": task["scheduled_for"].isoformat(),
            "color": colors.get(task["status"], "#6c757d"),
            "url": reverse(task_route, args=[task["id"]]),
        }
        for task in tasks
    ]
