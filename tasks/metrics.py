import csv
from datetime import date, datetime, time, timedelta

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.utils import timezone

from tasks.models import Task
from tasks.queries import task_counts


USER_LABELS = {
    "total": "Total de tarefas",
    "done": "Concluídas",
    "overdue": "Atrasadas",
    "upcoming": "Próximas",
}
SYSTEM_LABELS = {
    "accounts": "Contas cadastradas",
    "active_accounts": "Contas que criaram tarefas",
    "created": "Tarefas criadas",
    "completed": "Tarefas concluídas",
}


class MetricsPeriodForm(forms.Form):
    inicio = forms.DateField(
        label="Data inicial",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}),
    )
    fim = forms.DateField(
        label="Data final",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}),
    )

    def clean(self):
        values = super().clean()
        start = values.get("inicio")
        end = values.get("fim")
        if start and end:
            if end < start:
                self.add_error("fim", "A data final deve ser igual ou posterior à inicial.")
            elif end == date.max or (end - start).days >= 366:
                self.add_error("fim", "Informe um período de até 366 dias com data final válida.")
        return values


def metrics_period(params):
    if "inicio" not in params and "fim" not in params:
        today = timezone.localdate()
        params = {"inicio": today - timedelta(days=29), "fim": today}
    return MetricsPeriodForm(params)


def in_period(queryset, field, start, stop):
    return queryset.filter(**{f"{field}__gte": start, f"{field}__lt": stop})


def counts_by_date(queryset, field, **counts):
    return (
        queryset.order_by()
        .annotate(day=TruncDate(field))
        .values("day")
        .annotate(**counts)
    )


def system_metrics(start, stop, rows):
    users = in_period(get_user_model().objects.all(), "created_at", start, stop)
    tasks = in_period(Task.objects.all(), "created_at", start, stop)
    completed = in_period(Task.objects.all(), "completed_at", start, stop)
    for row in counts_by_date(users, "created_at", accounts=Count("pk")):
        rows[row.pop("day")].update(row)
    for row in counts_by_date(
        tasks, "created_at", created=Count("pk"), active_accounts=Count("owner", distinct=True)
    ):
        rows[row.pop("day")].update(row)
    for row in counts_by_date(completed, "completed_at", completed=Count("pk")):
        rows[row.pop("day")].update(row)
    return tasks.aggregate(active_accounts=Count("owner", distinct=True))


def metrics_report(user, inicio, fim):
    stop_date = fim + timedelta(days=1)
    start = timezone.make_aware(datetime.combine(inicio, time.min))
    stop = timezone.make_aware(datetime.combine(stop_date, time.min))
    labels = SYSTEM_LABELS if user.is_superuser else USER_LABELS
    rows = {
        inicio + timedelta(days=offset): dict.fromkeys(labels, 0)
        for offset in range((stop_date - inicio).days)
    }

    if user.is_superuser:
        period_totals = system_metrics(start, stop, rows)
    else:
        tasks = in_period(Task.objects.filter(owner=user), "scheduled_for", start, stop)
        for row in counts_by_date(tasks, "scheduled_for", **task_counts(timezone.now())):
            rows[row.pop("day")].update(row)
        period_totals = {}

    totals = {key: sum(row[key] for row in rows.values()) for key in labels}
    totals.update(period_totals)
    return {
        "inicio": inicio,
        "fim": fim,
        "labels": labels,
        "totals": totals,
        "daily": [{"date": day, **row} for day, row in rows.items()],
    }


def metrics_csv(report):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="rotina-metricas.csv"'
    writer = csv.writer(response)
    labels = report["labels"]
    writer.writerow(["Data", *labels.values()])
    for row in report["daily"]:
        writer.writerow([row["date"].isoformat(), *(row[key] for key in labels)])
    writer.writerow(["Total do período", *(report["totals"][key] for key in labels)])
    return response
