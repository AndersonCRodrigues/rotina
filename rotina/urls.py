"""URLconf raiz do projeto Rotina."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("contas/", include("accounts.urls")),
    path("tarefas/", include("tasks.urls")),
    path("api/", include("tasks.api_urls")),
    path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),
]

if settings.DEBUG:  # pragma: no cover — Django força DEBUG=False nos testes;
    # bloco padrão de serving de estáticos em dev sem proxy reverso.
    from django.conf.urls.static import static

    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
