from django.urls import include, path
from rest_framework.routers import DefaultRouter

from accounts.api_views import (
    CurrentUserView,
    RegistrationView,
    TokenLoginView,
    TokenLogoutView,
)
from tasks.api_views import CalendarEventsView, TaskSummaryView, TaskViewSet

app_name = "api"
router = DefaultRouter()
router.register("tarefas", TaskViewSet, basename="task")

urlpatterns = [
    path("cadastro/", RegistrationView.as_view(), name="register"),
    path("login/", TokenLoginView.as_view(), name="login"),
    path("logout/", TokenLogoutView.as_view(), name="logout"),
    path("me/", CurrentUserView.as_view(), name="me"),
    path("tarefas/resumo/", TaskSummaryView.as_view(), name="task_summary"),
    path("tarefas/calendario/eventos.json", CalendarEventsView.as_view(), name="calendar_events"),
    path("", include(router.urls)),
]
