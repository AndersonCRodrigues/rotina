from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from tasks.forms import TaskForm
from tasks.models import Task


class OwnedQuerysetMixin(LoginRequiredMixin):
    """Garante que toda query/gravação fica restrita ao usuário logado —
    evita que um usuário acesse/edite tarefas de outro só trocando o ID
    na URL (IDOR).
    """

    def get_queryset(self):
        return super().get_queryset().filter(owner=self.request.user)


class DashboardView(LoginRequiredMixin, ListView):
    model = Task
    template_name = "tasks/dashboard.html"
    context_object_name = "tasks"
    paginate_by = 10

    def get_queryset(self):
        return Task.objects.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        now = timezone.now()
        ctx["stats"] = {
            "total": qs.count(),
            "done": qs.filter(status=Task.Status.DONE).count(),
            "overdue": qs.exclude(status=Task.Status.DONE).filter(scheduled_for__lt=now).count(),
            "upcoming": qs.exclude(status=Task.Status.DONE).filter(scheduled_for__gte=now).count(),
        }
        return ctx


class TaskCreateView(LoginRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = "tasks/task_form.html"
    success_url = reverse_lazy("tasks:dashboard")

    def form_valid(self, form):
        form.instance.owner = self.request.user
        messages.success(self.request, "Tarefa criada com sucesso.")
        return super().form_valid(form)


class TaskUpdateView(OwnedQuerysetMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = "tasks/task_form.html"
    success_url = reverse_lazy("tasks:dashboard")

    def form_valid(self, form):
        original = Task.objects.get(pk=form.instance.pk, owner=self.request.user)
        reminder_fields = ("scheduled_for", "remind_enabled", "remind_minutes_before")
        if any(getattr(original, field) != form.cleaned_data[field] for field in reminder_fields):
            form.instance.reminder_sent_at = None
        messages.success(self.request, "Tarefa atualizada.")
        return super().form_valid(form)


class TaskDeleteView(OwnedQuerysetMixin, DeleteView):
    model = Task
    template_name = "tasks/task_confirm_delete.html"
    success_url = reverse_lazy("tasks:dashboard")

    def form_valid(self, form):
        messages.success(self.request, "Tarefa removida.")
        return super().form_valid(form)


class TaskCompleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk, owner=request.user)
        task.mark_complete()
        messages.success(request, f'Tarefa "{task.title}" cumprida com sucesso.')
        return redirect("tasks:dashboard")


class CalendarView(LoginRequiredMixin, TemplateView):
    template_name = "tasks/calendar.html"


class CalendarEventsJsonView(LoginRequiredMixin, View):
    """Alimenta o FullCalendar (front-end) com as tarefas do usuário logado
    no formato de evento esperado pela biblioteca.
    """

    def get(self, request):
        tasks = Task.objects.filter(owner=request.user)
        colors = {
            Task.Status.TODO: "#6c757d",
            Task.Status.IN_PROGRESS: "#0d6efd",
            Task.Status.DONE: "#198754",
        }
        events = [
            {
                "id": task.pk,
                "title": task.title,
                "start": task.scheduled_for.isoformat(),
                "color": colors.get(task.status, "#6c757d"),
                "url": reverse("tasks:task_update", args=[task.pk]),
            }
            for task in tasks
        ]
        return JsonResponse(events, safe=False)
