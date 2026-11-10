from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from tasks.models import Task

User = get_user_model()


class TaskAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="api_user", email="api@example.com", password="SenhaForte!2026"
        )
        self.other = User.objects.create_user(
            username="other", email="other@example.com", password="SenhaForte!2026"
        )
        self.client = APIClient()
        self.list_url = reverse("api:task-list")
        self.mine = Task.objects.create(
            owner=self.user, title="Minha tarefa", notes="nota secreta",
            scheduled_for=timezone.now() + timezone.timedelta(days=2),
        )
        self.foreign = Task.objects.create(
            owner=self.other, title="Tarefa alheia",
            scheduled_for=timezone.now() + timezone.timedelta(days=1),
        )

    def authenticate(self):
        self.client.force_login(self.user)

    def test_anonymous_requests_are_forbidden(self):
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
        self.assertEqual(self.client.post(self.list_url, {}, format="json").status_code, 403)
        self.assertEqual(self.client.get(reverse("api:me")).status_code, 403)

    def test_me_returns_only_current_user(self):
        self.authenticate()
        response = self.client.get(reverse("api:me"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {
            "id": self.user.pk, "username": "api_user", "email": "api@example.com"
        })

    def test_list_only_own_tasks(self):
        self.authenticate()
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.data]
        self.assertEqual(ids, [self.mine.pk])
        self.assertNotIn("owner", response.data[0])
        self.assertNotIn("reminder_sent_at", response.data[0])
        self.assertEqual(response.data[0]["notes"], "nota secreta")

    def test_detail_of_other_user_is_404(self):
        self.authenticate()
        self.assertEqual(
            self.client.get(reverse("api:task-detail", args=[self.foreign.pk])).status_code,
            404,
        )

    def test_create_sets_authenticated_owner_even_with_injected_owner(self):
        self.authenticate()
        response = self.client.post(self.list_url, {
            "title": "Nova via API", "notes": "texto sensível",
            "scheduled_for": (timezone.now() + timezone.timedelta(days=3)).isoformat(),
            "status": "todo", "owner": self.other.pk,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        task = Task.objects.get(pk=response.data["id"])
        self.assertEqual(task.owner, self.user)
        self.assertEqual(task.notes, "texto sensível")
        with connection.cursor() as cursor:
            cursor.execute("SELECT notes FROM tasks_task WHERE id = %s", [task.pk])
            self.assertNotEqual(cursor.fetchone()[0], "texto sensível")

    def test_invalid_reminder_needs_offset(self):
        self.authenticate()
        response = self.client.post(self.list_url, {
            "title": "Inválida",
            "scheduled_for": (timezone.now() + timezone.timedelta(days=3)).isoformat(),
            "remind_enabled": True,
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("remind_minutes_before", response.data)

    def test_create_with_reminder_and_read_computed_field(self):
        self.authenticate()
        when = timezone.now() + timezone.timedelta(days=3)
        response = self.client.post(self.list_url, {
            "title": "Lembrar", "scheduled_for": when.isoformat(),
            "remind_enabled": True, "remind_minutes_before": 60,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNotNone(response.data["remind_at"])

    def test_patch_and_put_own_task(self):
        self.authenticate()
        url = reverse("api:task-detail", args=[self.mine.pk])
        patch = self.client.patch(url, {"title": "Alterada"}, format="json")
        self.assertEqual(patch.status_code, 200, patch.data)
        updated = self.client.put(url, {
            "title": "Substituída", "scheduled_for": (
                timezone.now() + timezone.timedelta(days=1)
            ).isoformat(), "status": "in_progress",
        }, format="json")
        self.assertEqual(updated.status_code, 200, updated.data)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.title, "Substituída")

    def test_patch_invalid_reminder_rule_and_valid_retry(self):
        self.authenticate()
        url = reverse("api:task-detail", args=[self.mine.pk])
        bad = self.client.patch(url, {"remind_enabled": True}, format="json")
        self.assertEqual(bad.status_code, 400)
        good = self.client.patch(url, {
            "remind_enabled": True, "remind_minutes_before": 30
        }, format="json")
        self.assertEqual(good.status_code, 200, good.data)

    def test_search_status_and_ordering_filters(self):
        self.authenticate()
        Task.objects.create(owner=self.user, title="Reunião", status="done",
                            scheduled_for=timezone.now() + timezone.timedelta(days=3))
        response = self.client.get(self.list_url, {
            "search": "Reunião", "status": "done", "ordering": "-scheduled_for"
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "Reunião")

    def test_completion_uses_existing_model_method(self):
        self.authenticate()
        url = reverse("api:task-concluir", args=[self.mine.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url, {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, Task.Status.DONE)
        self.assertIsNotNone(self.mine.completed_at)

    def test_foreign_updates_deletes_and_completion_are_404(self):
        self.authenticate()
        detail = reverse("api:task-detail", args=[self.foreign.pk])
        self.assertEqual(self.client.patch(detail, {"title": "hack"}, format="json").status_code, 404)
        self.assertEqual(self.client.put(detail, {"title": "hack"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(detail).status_code, 404)
        self.assertEqual(self.client.post(
            reverse("api:task-concluir", args=[self.foreign.pk]), {}, format="json"
        ).status_code, 404)
        self.foreign.refresh_from_db()
        self.assertEqual(self.foreign.title, "Tarefa alheia")

    def test_delete_own_task(self):
        self.authenticate()
        response = self.client.delete(reverse("api:task-detail", args=[self.mine.pk]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Task.objects.filter(pk=self.mine.pk).exists())

    def test_csrf_is_required_for_authenticated_writes(self):
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        response = csrf_client.post(self.list_url, {
            "title": "Sem token", "scheduled_for": timezone.now().isoformat()
        }, format="json")
        self.assertEqual(response.status_code, 403)
        html_response = csrf_client.get(reverse("tasks:task_create"))
        self.assertEqual(html_response.status_code, 200)
        token = csrf_client.cookies["csrftoken"].value
        response = csrf_client.post(self.list_url, {
            "title": "Com token", "scheduled_for": timezone.now().isoformat()
        }, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 201, response.data)

    def test_existing_html_routes_remain_available(self):
        self.authenticate()
        self.assertEqual(self.client.get(reverse("tasks:dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("tasks:calendar")).status_code, 200)
        self.assertEqual(self.client.get(reverse("tasks:task_create")).status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 302)


class TaskAPIReminderRegressionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="regression", email="regression@example.com", password="SenhaForte!2026"
        )
        self.client = APIClient()
        self.client.force_login(self.user)
        self.task = Task.objects.create(
            owner=self.user, title="Lembrete",
            scheduled_for=timezone.now() + timezone.timedelta(days=1),
            remind_enabled=True, remind_minutes_before=30,
        )
        self.url = reverse("api:task-detail", args=[self.task.pk])

    def test_rescheduling_clears_previous_reminder_dispatch(self):
        self.task.mark_reminder_sent()
        response = self.client.patch(self.url, {
            "scheduled_for": (timezone.now() + timezone.timedelta(days=2)).isoformat()
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertIsNone(self.task.reminder_sent_at)

    def test_title_change_keeps_reminder_dispatch(self):
        self.task.mark_reminder_sent()
        sent_at = self.task.reminder_sent_at
        response = self.client.patch(self.url, {"title": "Outro título"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.reminder_sent_at, sent_at)

    def test_disabling_reminder_clears_offset(self):
        response = self.client.patch(self.url, {"remind_enabled": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertFalse(self.task.remind_enabled)
        self.assertIsNone(self.task.remind_minutes_before)


class TaskHTMLReminderRegressionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="html_user", email="html@example.com", password="SenhaForte!2026"
        )
        self.client.force_login(self.user)
        self.task = Task.objects.create(
            owner=self.user, title="Agenda",
            scheduled_for=timezone.now() + timezone.timedelta(days=1),
            remind_enabled=True, remind_minutes_before=30,
        )
        self.task.mark_reminder_sent()
        self.url = reverse("tasks:task_update", args=[self.task.pk])

    def test_reschedule_in_html_allows_new_reminder(self):
        response = self.client.post(self.url, {
            "title": "Agenda", "notes": "", "status": "todo",
            "scheduled_for": "2026-12-20T10:00",
            "remind_enabled": "on", "remind_minutes_before": "30",
        })
        self.assertEqual(response.status_code, 302)
        self.task.refresh_from_db()
        self.assertIsNone(self.task.reminder_sent_at)

    def test_disabling_html_reminder_clears_offset(self):
        response = self.client.post(self.url, {
            "title": "Agenda", "notes": "", "status": "todo",
            "scheduled_for": "2026-12-20T10:00",
            "remind_minutes_before": "30",
        })
        self.assertEqual(response.status_code, 302)
        self.task.refresh_from_db()
        self.assertFalse(self.task.remind_enabled)
        self.assertIsNone(self.task.remind_minutes_before)
