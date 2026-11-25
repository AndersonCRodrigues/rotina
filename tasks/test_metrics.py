import csv
from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token

from tasks.models import Task


class MetricsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.user = users.create_user("member", "member@example.com")
        cls.other = users.create_user("other", "other@example.com")
        cls.admin = users.create_superuser("admin", "admin@example.com", "Admin!48Password")
        cls.start = datetime(2026, 11, 23, 3, tzinfo=dt_timezone.utc)
        users.filter(pk=cls.user.pk).update(created_at=cls.start)
        users.filter(pk=cls.other.pk).update(created_at=cls.start + timedelta(days=1))
        users.filter(pk=cls.admin.pk).update(created_at=cls.start - timedelta(seconds=1))

        overdue = Task.objects.create(
            owner=cls.user, title="Atrasada", scheduled_for=cls.start,
        )
        upcoming = Task.objects.create(
            owner=cls.user, title="Próxima", scheduled_for=cls.start + timedelta(days=1),
        )
        done = Task.objects.create(
            owner=cls.user, title="Concluída", scheduled_for=cls.start + timedelta(hours=1),
            status=Task.Status.DONE, completed_at=cls.start + timedelta(days=1),
        )
        foreign = Task.objects.create(
            owner=cls.other, title="Outra tarefa", scheduled_for=cls.start,
        )
        outside = Task.objects.create(
            owner=cls.user, title="Fora do período", scheduled_for=cls.start - timedelta(seconds=1),
        )
        boundary = Task.objects.create(
            owner=cls.user, title="Depois do período", scheduled_for=cls.start + timedelta(days=2),
        )
        Task.objects.filter(pk__in=[overdue.pk, done.pk, foreign.pk]).update(created_at=cls.start)
        Task.objects.filter(pk=upcoming.pk).update(created_at=cls.start + timedelta(days=1))
        Task.objects.filter(pk__in=[outside.pk, boundary.pk]).update(
            created_at=cls.start - timedelta(seconds=1)
        )

        cls.user_token = Token.objects.create(user=cls.user)
        cls.admin_token = Token.objects.create(user=cls.admin)

    def setUp(self):
        self.period = {"inicio": "2026-11-23", "fim": "2026-11-24"}
        self.web = reverse("tasks:metrics")
        self.web_csv = reverse("tasks:metrics_csv")
        self.api = reverse("api:metrics")
        self.api_csv = reverse("api:metrics_csv")
        self.user_headers = {"HTTP_AUTHORIZATION": f"Token {self.user_token.key}"}
        self.admin_headers = {"HTTP_AUTHORIZATION": f"Token {self.admin_token.key}"}
        now = patch("tasks.metrics.timezone.now", return_value=self.start + timedelta(hours=2))
        now.start()
        self.addCleanup(now.stop)

    def test_requires_session_on_web_and_token_on_api(self):
        for url in (self.web, self.web_csv):
            self.assertEqual(self.client.get(url).status_code, 302)
        for url in (self.api, self.api_csv):
            self.assertEqual(self.client.get(url).status_code, 401)
        csv_error = self.client.get(self.api_csv, HTTP_ACCEPT="text/csv")
        self.assertEqual(csv_error.status_code, 401)
        self.assertContains(csv_error, "detail,", status_code=401)

    def test_user_dashboard_and_csv_render_filtered_values(self):
        self.client.force_login(self.user)
        response = self.client.get(self.web, self.period)
        self.assertContains(response, "Minhas métricas")
        self.assertContains(response, "Tarefas agendadas por dia")
        self.assertContains(response, 'value="2026-11-23"')
        self.assertEqual(
            response.context["report"]["totals"], {"total": 3, "done": 1, "overdue": 1, "upcoming": 1}
        )
        export = self.client.get(self.web_csv, self.period)
        self.assertEqual(export.status_code, 200)
        self.assertEqual(export["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment", export["Content-Disposition"])
        self.assertEqual(list(csv.reader(StringIO(export.content.decode()))), [
            ["Data", "Total de tarefas", "Concluídas", "Atrasadas", "Próximas"],
            ["2026-11-23", "2", "1", "1", "0"],
            ["2026-11-24", "1", "0", "0", "1"],
            ["Total do período", "3", "1", "1", "1"],
        ])
        api_export = self.client.get(
            self.api_csv, self.period, HTTP_ACCEPT="text/csv", **self.user_headers,
        )
        self.assertEqual(api_export.status_code, 200)
        self.assertEqual(api_export.content, export.content)

    def test_dashboard_defaults_to_last_30_local_days_and_includes_empty_days(self):
        self.client.force_login(self.user)
        response = self.client.get(self.web)
        self.assertEqual(response.status_code, 200)
        report = response.context["report"]
        self.assertEqual(report["fim"].isoformat(), "2026-11-23")
        self.assertEqual(len(report["daily"]), 30)
        self.assertEqual(report["daily"][0]["total"], 0)

        response = self.client.get(self.web, {"inicio": "2026-10-01", "fim": "2026-11-24"})
        self.assertContains(response, "Tarefas agendadas por intervalo")
        self.assertLessEqual(len(response.context["chart_bars"]), 31)
        self.assertEqual(len(response.context["report"]["daily"]), 55)

    def test_invalid_period_is_rejected_on_web_and_api(self):
        self.client.force_login(self.user)
        for params in (
            {"inicio": "2026-11-23"},
            {"inicio": "invalid", "fim": "2026-11-24"},
            {"inicio": "2026-11-24", "fim": "2026-11-23"},
            {"inicio": "2025-01-01", "fim": "2026-11-24"},
            {"inicio": "9999-12-31", "fim": "9999-12-31"},
        ):
            with self.subTest(params=params):
                for url in (self.web, self.web_csv):
                    self.assertEqual(self.client.get(url, params).status_code, 400)
                for url in (self.api, self.api_csv):
                    self.assertEqual(self.client.get(url, params, **self.user_headers).status_code, 400)
        csv_error = self.client.get(
            self.api_csv, {"inicio": "invalid"}, HTTP_ACCEPT="text/csv", **self.user_headers,
        )
        self.assertContains(csv_error, "inicio,", status_code=400)

    def test_admin_sees_only_system_dashboard_on_web(self):
        login = self.client.post(reverse("accounts:login") + "?next=/tarefas/calendario/", {
            "username": self.admin.username, "password": "Admin!48Password",
        })
        self.assertRedirects(login, self.web, fetch_redirect_response=False)
        for path in ("/", "/tarefas/", "/tarefas/nova/", "/tarefas/calendario/", "/contas/cadastro/"):
            self.assertRedirects(self.client.get(path), self.web, fetch_redirect_response=False)
        self.assertEqual(self.client.get("/admin/").status_code, 404)

        system = self.client.get(self.web, self.period)
        self.assertContains(system, "Métricas do sistema")
        self.assertContains(system, "Tarefas criadas por dia")
        self.assertNotContains(system, reverse("tasks:task_create"))
        self.assertEqual(system.context["report"]["totals"], {
            "accounts": 2, "active_accounts": 2, "created": 4, "completed": 1,
        })
        self.assertRedirects(self.client.post(reverse("accounts:logout")), "/")

    def test_reports_use_fixed_number_of_queries_and_deduplicate_active_accounts(self):
        with self.assertNumQueries(2):
            user_response = self.client.get(self.api, self.period, **self.user_headers)
        self.assertEqual(user_response.status_code, 200)
        self.assertEqual(user_response.json()["totals"], {
            "total": 3, "done": 1, "overdue": 1, "upcoming": 1,
        })
        with self.assertNumQueries(5):
            admin_response = self.client.get(self.api, self.period, **self.admin_headers)
        self.assertEqual(admin_response.status_code, 200)
        report = admin_response.json()
        self.assertEqual(report["totals"], {
            "accounts": 2, "active_accounts": 2, "created": 4, "completed": 1,
        })
        self.assertEqual([row["active_accounts"] for row in report["daily"]], [2, 1])
        with self.assertNumQueries(5):
            export = self.client.get(self.api_csv, self.period, **self.admin_headers)
        self.assertEqual(export.status_code, 200)
        self.assertEqual(list(csv.reader(StringIO(export.content.decode())))[-1], [
            "Total do período", "2", "2", "4", "1",
        ])
