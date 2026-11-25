import os
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from accounts.models import User


class BootstrapSuperadminTests(TestCase):
    def bootstrap(self, email="", password=""):
        with patch.dict(os.environ, SUPERADMIN_EMAIL=email, SUPERADMIN_PASSWORD=password):
            call_command("bootstrap_superadmin")

    def test_creates_superadmin_and_preserves_password_on_restart(self):
        self.bootstrap(" Admin@Example.com ", "Provisioned!48Pass")
        self.bootstrap("admin@example.com", "Changed!93Pass")

        user = User.objects.get()
        self.assertEqual(user.email, "admin@example.com")
        self.assertEqual(user.username, user.email)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password("Provisioned!48Pass"))
        self.assertTrue(self.client.login(username=user.email, password="Provisioned!48Pass"))

    def test_leaves_normal_account_unchanged(self):
        user = User.objects.create_user("existing", "Admin@Example.com", "Existing!93Pass")
        with self.assertRaises(CommandError):
            self.bootstrap("admin@example.com", "Provisioned!48Pass")
        user.refresh_from_db()
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)
        self.assertTrue(user.check_password("Existing!93Pass"))

    def test_skips_without_credentials(self):
        self.bootstrap()
        self.assertFalse(User.objects.exists())

    def test_rejects_incomplete_or_invalid_credentials(self):
        for email, password in (
            ("admin@example.com", ""),
            ("invalid-email", "Provisioned!48Pass"),
            ("admin@example.com", "123"),
        ):
            with self.subTest(email=email), self.assertRaises(CommandError):
                self.bootstrap(email, password)
        self.assertFalse(User.objects.exists())

    def test_rejects_username_collision(self):
        User.objects.create_user("admin@example.com", "other@example.com")
        with self.assertRaises(CommandError):
            self.bootstrap("admin@example.com", "Provisioned!48Pass")
        self.assertEqual(User.objects.count(), 1)
