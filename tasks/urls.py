from django.urls import path

from tasks import views

app_name = "tasks"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("nova/", views.TaskCreateView.as_view(), name="task_create"),
    path("<int:pk>/editar/", views.TaskUpdateView.as_view(), name="task_update"),
    path("<int:pk>/excluir/", views.TaskDeleteView.as_view(), name="task_delete"),
    path("<int:pk>/concluir/", views.TaskCompleteView.as_view(), name="task_complete"),
    path("calendario/", views.CalendarView.as_view(), name="calendar"),
    path("calendario/eventos.json", views.CalendarEventsJsonView.as_view(), name="calendar_events"),
]
