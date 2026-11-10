from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
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
        token, _ = Token.objects.get_or_create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_anonymous_requests_are_unauthorized(self):
        self.assertEqual(self.client.get(self.list_url).status_code, 401)
        self.assertEqual(self.client.post(self.list_url, {}, format="json").status_code, 401)
        self.assertEqual(self.client.get(reverse("api:me")).status_code, 401)

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

    def test_token_authentication_does_not_require_csrf(self):
        csrf_client = APIClient(enforce_csrf_checks=True)
        token = Token.objects.get_or_create(user=self.user)[0]
        csrf_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = csrf_client.post(self.list_url, {
            "title": "Com token", "scheduled_for": timezone.now().isoformat()
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)

    def test_session_alone_does_not_authenticate_api(self):
        client = APIClient()
        client.force_login(self.user)
        self.assertEqual(client.get(self.list_url).status_code, 401)

    def test_invalid_token_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token invalido")
        self.assertEqual(self.client.get(self.list_url).status_code, 401)

    def test_existing_html_routes_remain_available(self):
        self.authenticate()
        self.client.force_login(self.user)
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
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=self.user)[0].key}")
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


class TaskStatusConsistencyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="status_user", email="status@example.com", password="SenhaForte!2026"
        )
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=self.user)[0].key}")
        self.client.force_login(self.user)
        self.url = reverse("api:task-list")

    def test_api_create_completed_task_sets_timestamp(self):
        response = self.client.post(self.url, {
            "title": "Feita na criação",
            "scheduled_for": (timezone.now() + timezone.timedelta(days=1)).isoformat(),
            "status": Task.Status.DONE,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        task = Task.objects.get(pk=response.data["id"])
        self.assertIsNotNone(task.completed_at)
        self.assertEqual(task.status, Task.Status.DONE)

    def test_api_patch_completion_and_reopening(self):
        task = Task.objects.create(
            owner=self.user, title="Andamento", scheduled_for=timezone.now(),
            remind_enabled=True, remind_minutes_before=30,
        )
        detail = reverse("api:task-detail", args=[task.pk])
        response = self.client.patch(detail, {"status": Task.Status.DONE}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        task.refresh_from_db()
        self.assertIsNotNone(task.completed_at)
        task.mark_reminder_sent()
        response = self.client.patch(detail, {"status": Task.Status.TODO}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        task.refresh_from_db()
        self.assertIsNone(task.completed_at)
        self.assertIsNone(task.reminder_sent_at)

    def test_html_create_completed_task_sets_timestamp(self):
        response = self.client.post(reverse("tasks:task_create"), {
            "title": "Feita no formulário", "notes": "", "status": "done",
            "scheduled_for": "2026-12-20T10:00",
        })
        self.assertEqual(response.status_code, 302)
        task = Task.objects.get(title="Feita no formulário")
        self.assertIsNotNone(task.completed_at)

    def test_html_completion_and_reopening(self):
        task = Task.objects.create(owner=self.user, title="Form", scheduled_for=timezone.now())
        url = reverse("tasks:task_update", args=[task.pk])
        base = {"title": "Form", "notes": "", "scheduled_for": "2026-12-20T10:00"}
        response = self.client.post(url, {**base, "status": "done"})
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertIsNotNone(task.completed_at)
        response = self.client.post(url, {**base, "status": "todo"})
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertIsNone(task.completed_at)


class DRFTokenAuthenticationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="auth_user", email="auth@example.com", password="SenhaForte!2026"
        )
        self.client = APIClient(enforce_csrf_checks=True)
        self.login_url = reverse("api:login")
        self.logout_url = reverse("api:logout")
        self.me_url = reverse("api:me")

    def login(self):
        return self.client.post(self.login_url, {
            "username": "auth_user", "password": "SenhaForte!2026"
        }, format="json")

    def test_login_returns_drf_token_and_reuses_it(self):
        response = self.login()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["token"], Token.objects.get(user=self.user).key)
        self.assertEqual(self.login().data["token"], response.data["token"])

    def test_login_with_invalid_credentials_is_rejected(self):
        response = self.client.post(self.login_url, {
            "username": "auth_user", "password": "incorreta"
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_login_requires_post(self):
        self.assertEqual(self.client.get(self.login_url).status_code, 405)

    def test_login_rejects_inactive_user(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(self.login().status_code, 400)
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_me_requires_token_even_with_authenticated_django_session(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.me_url).status_code, 401)

    def test_me_returns_current_user_from_token(self):
        token = self.login().data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {
            "id": self.user.id, "username": self.user.username, "email": self.user.email
        })

    def test_logout_revokes_token_and_new_login_gets_new_one(self):
        old_token = self.login().data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {old_token}")
        response = self.client.post(self.logout_url, {}, format="json")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Token.objects.filter(key=old_token).exists())
        self.assertEqual(self.client.get(self.me_url).status_code, 401)
        self.client.credentials()
        new_token = self.login().data["token"]
        self.assertNotEqual(old_token, new_token)

    def test_logout_requires_token_and_post(self):
        self.assertEqual(self.client.post(self.logout_url, {}, format="json").status_code, 401)
        token = self.login().data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(self.client.get(self.logout_url).status_code, 405)

    def test_other_users_token_does_not_access_my_tasks(self):
        second = User.objects.create_user(
            username="second", email="second@example.com", password="SenhaForte!2026"
        )
        mine = Task.objects.create(owner=self.user, title="Privada", scheduled_for=timezone.now())
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=second).key}")
        self.assertEqual(self.client.get(reverse("api:task-list")).data, [])
        self.assertEqual(self.client.get(reverse("api:task-detail", args=[mine.pk])).status_code, 404)
