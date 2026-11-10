from django.urls import include, path
from rest_framework.routers import DefaultRouter

from accounts.api_views import CurrentUserView
from tasks.api_views import TaskViewSet

app_name = "api"
router = DefaultRouter()
router.register("tarefas", TaskViewSet, basename="task")

urlpatterns = [
    path("me/", CurrentUserView.as_view(), name="me"),
    path("", include(router.urls)),
]
