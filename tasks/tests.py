import io
import json

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from tasks.forms import TaskForm
from tasks.models import Task

User = get_user_model()


def make_user(username="u", email=None):
    return User.objects.create_user(
        username=username, email=email or f"{username}@example.com", password="SenhaForte!2026"
    )


class TaskModelTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def _make_task(self, **kwargs):
        defaults = dict(owner=self.user, title="Tarefa", scheduled_for=timezone.now())
        defaults.update(kwargs)
        return Task.objects.create(**defaults)

    def test_str_returns_title(self):
        task = self._make_task(title="Reunião")
        self.assertEqual(str(task), "Reunião")

    def test_is_overdue_true_for_past_pending_task(self):
        task = self._make_task(scheduled_for=timezone.now() - timezone.timedelta(days=1))
        self.assertTrue(task.is_overdue)

    def test_is_overdue_false_for_future_task(self):
        task = self._make_task(scheduled_for=timezone.now() + timezone.timedelta(days=1))
        self.assertFalse(task.is_overdue)

    def test_is_overdue_false_when_done_even_if_past(self):
        task = self._make_task(
            scheduled_for=timezone.now() - timezone.timedelta(days=1), status=Task.Status.DONE
        )
        self.assertFalse(task.is_overdue)

    def test_remind_at_none_when_disabled(self):
        task = self._make_task(remind_enabled=False, remind_minutes_before=30)
        self.assertIsNone(task.remind_at)

    def test_remind_at_none_when_no_offset_chosen(self):
        task = self._make_task(remind_enabled=True, remind_minutes_before=None)
        self.assertIsNone(task.remind_at)

    def test_remind_at_computed_correctly(self):
        scheduled = timezone.now() + timezone.timedelta(hours=2)
        task = self._make_task(scheduled_for=scheduled, remind_enabled=True, remind_minutes_before=60)
        self.assertEqual(task.remind_at, scheduled - timezone.timedelta(minutes=60))

    def test_mark_complete_sets_status_and_timestamp(self):
        task = self._make_task()
        self.assertIsNone(task.completed_at)
        task.mark_complete()
        self.assertEqual(task.status, Task.Status.DONE)
        self.assertIsNotNone(task.completed_at)

    def test_mark_reminder_sent_sets_timestamp(self):
        task = self._make_task(remind_enabled=True, remind_minutes_before=10)
        self.assertIsNone(task.reminder_sent_at)
        task.mark_reminder_sent()
        self.assertIsNotNone(task.reminder_sent_at)

    def test_notes_are_encrypted_at_rest(self):
        secret = "informação sensível do usuário"
        task = self._make_task(notes=secret)

        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("SELECT notes FROM tasks_task WHERE id = %s", [task.id])
            raw_notes = cur.fetchone()[0]
        self.assertNotEqual(raw_notes, secret)

        task.refresh_from_db()
        self.assertEqual(task.notes, secret)


class TaskQuerySetPendingRemindersTests(TestCase):
    """Cobre o método usado pelo worker isoladamente do management command."""

    def setUp(self):
        self.user = make_user()
        self.now = timezone.now()

    def test_due_task_with_reminder_is_returned(self):
        task = Task.objects.create(
            owner=self.user, title="Vencida",
            scheduled_for=self.now + timezone.timedelta(minutes=5),
            remind_enabled=True, remind_minutes_before=10,
        )
        due = Task.objects.pending_reminders(as_of=self.now)
        self.assertIn(task, due)

    def test_future_reminder_is_not_returned(self):
        Task.objects.create(
            owner=self.user, title="Futura",
            scheduled_for=self.now + timezone.timedelta(hours=5),
            remind_enabled=True, remind_minutes_before=10,
        )
        self.assertEqual(Task.objects.pending_reminders(as_of=self.now), [])

    def test_done_task_is_not_returned(self):
        Task.objects.create(
            owner=self.user, title="Concluida",
            scheduled_for=self.now + timezone.timedelta(minutes=5),
            remind_enabled=True, remind_minutes_before=10, status=Task.Status.DONE,
        )
        self.assertEqual(Task.objects.pending_reminders(as_of=self.now), [])

    def test_task_without_reminder_is_not_returned(self):
        Task.objects.create(owner=self.user, title="Sem lembrete", scheduled_for=self.now)
        self.assertEqual(Task.objects.pending_reminders(as_of=self.now), [])

    def test_already_notified_task_is_not_returned_again(self):
        task = Task.objects.create(
            owner=self.user, title="Ja notificada",
            scheduled_for=self.now + timezone.timedelta(minutes=5),
            remind_enabled=True, remind_minutes_before=10,
        )
        task.mark_reminder_sent()
        self.assertEqual(Task.objects.pending_reminders(as_of=self.now), [])


class SendRemindersCommandTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.now = timezone.now()

    def test_run_once_no_pending_reminders(self):
        out = io.StringIO()
        call_command("send_reminders", stdout=out)
        self.assertIn("Nenhum lembrete pendente", out.getvalue())

    def test_run_once_notifies_and_marks_due_task(self):
        task = Task.objects.create(
            owner=self.user, title="Tarefa vencida",
            scheduled_for=self.now + timezone.timedelta(minutes=5),
            remind_enabled=True, remind_minutes_before=10,
        )
        out = io.StringIO()
        call_command("send_reminders", stdout=out)
        self.assertIn("1 lembrete(s) disparado(s)", out.getvalue())
        self.assertIn(task.title, out.getvalue())
        task.refresh_from_db()
        self.assertIsNotNone(task.reminder_sent_at)

    def test_run_once_does_not_duplicate_notification(self):
        Task.objects.create(
            owner=self.user, title="Tarefa vencida",
            scheduled_for=self.now + timezone.timedelta(minutes=5),
            remind_enabled=True, remind_minutes_before=10,
        )
        call_command("send_reminders", stdout=io.StringIO())
        out2 = io.StringIO()
        call_command("send_reminders", stdout=out2)
        self.assertIn("Nenhum lembrete pendente", out2.getvalue())

    def test_loop_runs_max_iterations_then_stops(self):
        out = io.StringIO()
        call_command(
            "send_reminders", "--loop", "--max-iterations", "3", "--interval", "0", stdout=out
        )
        self.assertEqual(out.getvalue().count("Nenhum lembrete pendente"), 3)

    def test_loop_keyboard_interrupt_is_handled_gracefully(self):
        """Simula Ctrl+C durante o sleep entre passadas do --loop."""
        out = io.StringIO()
        from unittest.mock import patch

        with patch("tasks.management.commands.send_reminders.time.sleep", side_effect=KeyboardInterrupt):
            call_command("send_reminders", "--loop", "--max-iterations", "5", stdout=out)
        # rodou a primeira passada antes de ser interrompido no sleep
        self.assertIn("Nenhum lembrete pendente", out.getvalue())
        self.assertIn("interrompido", out.getvalue().lower())


class TaskFormTests(TestCase):
    def test_valid_without_reminder(self):
        form = TaskForm(data={
            "title": "Tarefa", "notes": "", "scheduled_for": "2026-12-01T10:00",
            "status": "todo",
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_reminder_enabled_without_offset_is_invalid(self):
        form = TaskForm(data={
            "title": "Tarefa", "notes": "", "scheduled_for": "2026-12-01T10:00",
            "status": "todo", "remind_enabled": "on",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("remind_minutes_before", form.errors)

    def test_reminder_enabled_with_offset_is_valid(self):
        form = TaskForm(data={
            "title": "Tarefa", "notes": "", "scheduled_for": "2026-12-01T10:00",
            "status": "todo", "remind_enabled": "on", "remind_minutes_before": "60",
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_checkbox_field_gets_form_check_input_class(self):
        form = TaskForm()
        self.assertIn("form-check-input", form.fields["remind_enabled"].widget.attrs["class"])

    def test_text_field_gets_form_control_class(self):
        form = TaskForm()
        self.assertIn("form-control", form.fields["title"].widget.attrs["class"])


class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.login(username="u", password="SenhaForte!2026")
        self.now = timezone.now()

    def test_dashboard_stats_all_branches(self):
        Task.objects.create(owner=self.user, title="feita", scheduled_for=self.now, status=Task.Status.DONE)
        Task.objects.create(
            owner=self.user, title="atrasada",
            scheduled_for=self.now - timezone.timedelta(days=1), status=Task.Status.TODO,
        )
        Task.objects.create(
            owner=self.user, title="futura",
            scheduled_for=self.now + timezone.timedelta(days=1), status=Task.Status.TODO,
        )
        response = self.client.get(reverse("tasks:dashboard"))
        self.assertEqual(response.status_code, 200)
        stats = response.context["stats"]
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["done"], 1)
        self.assertEqual(stats["overdue"], 1)
        self.assertEqual(stats["upcoming"], 1)

    def test_dashboard_empty_state(self):
        response = self.client.get(reverse("tasks:dashboard"))
        self.assertContains(response, "ainda não tem tarefas")


class TaskCreateViewTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.login(username="u", password="SenhaForte!2026")

    def test_get_renders_form(self):
        response = self.client.get(reverse("tasks:task_create"))
        self.assertEqual(response.status_code, 200)

    def test_post_valid_creates_task_owned_by_current_user(self):
        response = self.client.post(reverse("tasks:task_create"), {
            "title": "Nova tarefa", "notes": "", "scheduled_for": "2026-12-01T10:00",
            "status": "todo",
        })
        self.assertRedirects(response, reverse("tasks:dashboard"))
        task = Task.objects.get(title="Nova tarefa")
        self.assertEqual(task.owner, self.user)

    def test_post_invalid_does_not_create(self):
        response = self.client.post(reverse("tasks:task_create"), {
            "title": "", "notes": "", "scheduled_for": "", "status": "todo",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Task.objects.exists())

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("tasks:task_create"))
        self.assertEqual(response.status_code, 302)


class TaskUpdateDeleteViewTests(TestCase):
    def setUp(self):
        self.user = make_user("u")
        self.other = make_user("v")
        self.client.login(username="u", password="SenhaForte!2026")
        self.task = Task.objects.create(owner=self.user, title="Minha", scheduled_for=timezone.now())
        self.foreign_task = Task.objects.create(owner=self.other, title="Alheia", scheduled_for=timezone.now())

    def test_owner_can_view_edit_form(self):
        response = self.client.get(reverse("tasks:task_update", args=[self.task.pk]))
        self.assertEqual(response.status_code, 200)

    def test_owner_can_update_task(self):
        response = self.client.post(reverse("tasks:task_update", args=[self.task.pk]), {
            "title": "Minha (editada)", "notes": "", "scheduled_for": "2026-12-01T10:00",
            "status": "todo",
        })
        self.assertRedirects(response, reverse("tasks:dashboard"))
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "Minha (editada)")

    def test_user_cannot_view_another_users_task_form(self):
        response = self.client.get(reverse("tasks:task_update", args=[self.foreign_task.pk]))
        self.assertEqual(response.status_code, 404)

    def test_user_cannot_update_another_users_task(self):
        response = self.client.post(reverse("tasks:task_update", args=[self.foreign_task.pk]), {
            "title": "Hackeada", "notes": "", "scheduled_for": "2026-12-01T10:00", "status": "todo",
        })
        self.assertEqual(response.status_code, 404)
        self.foreign_task.refresh_from_db()
        self.assertEqual(self.foreign_task.title, "Alheia")

    def test_owner_can_view_delete_confirmation(self):
        response = self.client.get(reverse("tasks:task_delete", args=[self.task.pk]))
        self.assertEqual(response.status_code, 200)

    def test_owner_can_delete_task(self):
        response = self.client.post(reverse("tasks:task_delete", args=[self.task.pk]))
        self.assertRedirects(response, reverse("tasks:dashboard"))
        self.assertFalse(Task.objects.filter(pk=self.task.pk).exists())

    def test_user_cannot_delete_another_users_task(self):
        response = self.client.post(reverse("tasks:task_delete", args=[self.foreign_task.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Task.objects.filter(pk=self.foreign_task.pk).exists())


class TaskCompleteViewTests(TestCase):
    def setUp(self):
        self.user = make_user("u")
        self.other = make_user("v")
        self.client.login(username="u", password="SenhaForte!2026")

    def test_owner_can_complete_task(self):
        task = Task.objects.create(owner=self.user, title="A concluir", scheduled_for=timezone.now())
        response = self.client.post(reverse("tasks:task_complete", args=[task.pk]), follow=True)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.DONE)
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("cumprida com sucesso" in m for m in messages))

    def test_user_cannot_complete_another_users_task(self):
        foreign_task = Task.objects.create(owner=self.other, title="Alheia", scheduled_for=timezone.now())
        response = self.client.post(reverse("tasks:task_complete", args=[foreign_task.pk]))
        self.assertEqual(response.status_code, 404)

    def test_requires_login(self):
        self.client.logout()
        task = Task.objects.create(owner=self.user, title="X", scheduled_for=timezone.now())
        response = self.client.post(reverse("tasks:task_complete", args=[task.pk]))
        self.assertEqual(response.status_code, 302)


class CalendarViewTests(TestCase):
    def setUp(self):
        self.user = make_user("u")
        self.other = make_user("v")
        self.client.login(username="u", password="SenhaForte!2026")

    def test_calendar_page_loads(self):
        response = self.client.get(reverse("tasks:calendar"))
        self.assertEqual(response.status_code, 200)

    def test_calendar_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("tasks:calendar"))
        self.assertEqual(response.status_code, 302)

    def test_events_json_only_returns_own_tasks_with_expected_shape(self):
        mine = Task.objects.create(
            owner=self.user, title="Minha", scheduled_for=timezone.now(), status=Task.Status.IN_PROGRESS
        )
        Task.objects.create(owner=self.other, title="Alheia", scheduled_for=timezone.now())

        response = self.client.get(reverse("tasks:calendar_events"))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], mine.pk)
        self.assertEqual(data[0]["title"], "Minha")
        self.assertEqual(data[0]["color"], "#0d6efd")

    def test_events_json_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("tasks:calendar_events"))
        self.assertEqual(response.status_code, 302)
