from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from tasks.forms import TaskForm, calendar_range
from tasks.models import Task
from tasks.queries import calendar_events, task_summary


class OwnedQuerysetMixin(LoginRequiredMixin):
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
        ctx["stats"] = task_summary(self.object_list)
        return ctx


class TaskCreateView(LoginRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = "tasks/task_form.html"
    success_url = reverse_lazy("tasks:dashboard")

    def form_valid(self, form):
        form.instance.owner = self.request.user
        if form.cleaned_data["status"] == Task.Status.DONE:
            form.instance.completed_at = timezone.now()
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
        new_status = form.cleaned_data["status"]
        if original.status == Task.Status.DONE and new_status != original.status:
            form.instance.reminder_sent_at = None
        if new_status == Task.Status.DONE:
            if original.status != Task.Status.DONE or original.completed_at is None:
                form.instance.completed_at = timezone.now()
        else:
            form.instance.completed_at = None
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
    def get(self, request):
        try:
            period = calendar_range(request.GET)
        except ValidationError as error:
            return JsonResponse(error.message_dict, status=400)
        return JsonResponse(calendar_events(request.user, "tasks:task_update", **period), safe=False)
