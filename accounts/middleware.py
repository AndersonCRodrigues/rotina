from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin


class SuperadminDashboardMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        route = request.resolver_match
        if not request.user.is_superuser or route.namespace not in {"core", "accounts", "tasks"}:
            return None
        if route.view_name in {"tasks:metrics", "tasks:metrics_csv", "accounts:logout"}:
            return None
        return redirect("tasks:metrics")
