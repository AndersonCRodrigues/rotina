from datetime import timedelta
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts.models import User
from tasks.models import Task


class RegistrationAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("api:register")
        self.payload = {
            "username": "new-user",
            "email": "New@Example.com",
            "password1": "Provisioned!48Pass",
            "password2": "Provisioned!48Pass",
            "is_staff": True,
            "is_superuser": True,
        }

    def test_registers_regular_account_that_can_log_in(self):
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, 201)
        user = User.objects.get()
        self.assertEqual(response.json(), {
            "id": user.pk, "username": "new-user", "email": "new@example.com",
        })
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password(self.payload["password1"]))
        login = self.client.post(reverse("api:login"), {
            "username": user.username, "password": self.payload["password1"],
        }, format="json")
        self.assertEqual(login.status_code, 200)
        self.assertIn("token", login.json())

    def test_rejects_missing_or_invalid_fields(self):
        for fields, error_field in (
            ({}, "username"),
            ({**self.payload, "email": "invalid"}, "email"),
            ({**self.payload, "password2": "Different!48Pass"}, "password2"),
            ({**self.payload, "password1": "123", "password2": "123"}, "password2"),
        ):
            with self.subTest(error_field=error_field):
                response = self.client.post(self.url, fields, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn(error_field, response.json())
        self.assertFalse(User.objects.exists())

    def test_rejects_duplicate_email_and_username(self):
        User.objects.create_user("new-user", "new@example.com")
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json())
        self.assertIn("username", response.json())

    @patch("accounts.api_views.RegisterForm.save", side_effect=IntegrityError)
    def test_handles_conflict_during_save(self, save):
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.exists())


class TaskReadAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user("mine", "mine@example.com")
        self.other = User.objects.create_user("other", "other@example.com")
        self.token = Token.objects.create(user=self.user)
        self.summary_url = reverse("api:task_summary")
        self.calendar_url = reverse("api:calendar_events")

    def test_requires_token(self):
        for url in (self.summary_url, self.calendar_url):
            self.assertEqual(self.client.get(url).status_code, 401)

    def test_returns_only_own_data_in_one_task_query_per_endpoint(self):
        now = timezone.now()
        overdue = Task.objects.create(
            owner=self.user, title="Atrasada", scheduled_for=now - timedelta(days=1),
        )
        Task.objects.create(owner=self.user, title="Próxima", scheduled_for=now + timedelta(days=1))
        Task.objects.create(owner=self.user, title="Feita", scheduled_for=now, status=Task.Status.DONE)
        foreign = Task.objects.create(owner=self.other, title="Alheia", scheduled_for=now)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        with self.assertNumQueries(2):
            summary = self.client.get(self.summary_url)
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json(), {"total": 3, "done": 1, "overdue": 1, "upcoming": 1})

        with self.assertNumQueries(2):
            calendar = self.client.get(self.calendar_url)
        self.assertEqual(calendar.status_code, 200)
        self.assertEqual(len(calendar.json()), 3)
        self.assertNotIn(foreign.pk, [event["id"] for event in calendar.json()])
        self.assertEqual(calendar.json()[0], {
            "id": overdue.pk,
            "title": overdue.title,
            "start": overdue.scheduled_for.isoformat(),
            "color": "#6c757d",
            "url": reverse("api:task-detail", args=[overdue.pk]),
        })
