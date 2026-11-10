from django.urls import include, path
from rest_framework.routers import DefaultRouter

from accounts.api_views import CurrentUserView, TokenLoginView, TokenLogoutView
from tasks.api_views import TaskViewSet

app_name = "api"
router = DefaultRouter()
router.register("tarefas", TaskViewSet, basename="task")

urlpatterns = [
    path("login/", TokenLoginView.as_view(), name="login"),
    path("logout/", TokenLogoutView.as_view(), name="logout"),
    path("me/", CurrentUserView.as_view(), name="me"),
    path("", include(router.urls)),
]
