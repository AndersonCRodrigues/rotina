import csv
from io import StringIO
from math import ceil

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views import View
from rest_framework import serializers
from rest_framework.renderers import BaseRenderer, BrowsableAPIRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from tasks.metrics import metrics_csv, metrics_period, metrics_report


class MetricsView(LoginRequiredMixin, View):
    export = False

    def get(self, request):
        form = metrics_period(request.GET)
        context = {"form": form}
        if not form.is_valid():
            return render(request, "tasks/metrics.html", context, status=400)

        report = metrics_report(request.user, **form.cleaned_data)
        if self.export:
            return metrics_csv(report)

        chart_key = "created" if request.user.is_superuser else "total"
        days = report["daily"]
        group_size = ceil(len(days) / 31)
        groups = [days[offset:offset + group_size] for offset in range(0, len(days), group_size)]
        bars = [
            (group[0]["date"], group[-1]["date"], sum(row[chart_key] for row in group))
            for group in groups
        ]
        chart_label = "Tarefas criadas" if request.user.is_superuser else "Tarefas agendadas"
        context.update(
            report=report,
            cards=[(label, report["totals"][key]) for key, label in report["labels"].items()],
            chart_label=f"{chart_label} por {'dia' if group_size == 1 else 'intervalo'}",
            chart_bars=bars,
            chart_max=max(1, max(value for _, _, value in bars)),
        )
        return render(request, "tasks/metrics.html", context)


class MetricsAPIView(APIView):
    export = False

    def get(self, request):
        form = metrics_period(request.query_params)
        if not form.is_valid():
            raise serializers.ValidationError(dict(form.errors))
        report = metrics_report(request.user, **form.cleaned_data)
        if self.export:
            return metrics_csv(report)
        return Response(report)


class MetricsCSVErrorRenderer(BaseRenderer):
    media_type = "text/csv"
    format = "csv"
    charset = "utf-8"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Campo", "Mensagem"])
        for field, errors in data.items():
            messages = errors if isinstance(errors, list) else [errors]
            writer.writerows((field, message) for message in messages)
        return output.getvalue()


class MetricsCSVAPIView(MetricsAPIView):
    export = True
    renderer_classes = [JSONRenderer, MetricsCSVErrorRenderer, BrowsableAPIRenderer]
