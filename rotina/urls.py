from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
    path("contas/", include("accounts.urls")),
    path("tarefas/", include("tasks.urls")),
    path("api/", include("tasks.api_urls")),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
