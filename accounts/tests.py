from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.forms import LoginForm, RegisterForm

User = get_user_model()


class UserModelTests(TestCase):
    def test_str_returns_username(self):
        user = User.objects.create_user(username="anderson", email="a@example.com", password="SenhaForte!2026")
        self.assertEqual(str(user), "anderson")


class RegisterFormTests(TestCase):
    def test_widgets_get_bootstrap_class(self):
        form = RegisterForm()
        for field in form.fields.values():
            self.assertIn("form-control", field.widget.attrs["class"])

    def test_valid_data_creates_clean_email(self):
        form = RegisterForm(data={
            "username": "anderson",
            "email": "  Anderson@Example.com  ",
            "password1": "SenhaForte!2026",
            "password2": "SenhaForte!2026",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["email"], "anderson@example.com")

    def test_duplicate_email_is_invalid(self):
        User.objects.create_user(username="existente", email="dup@example.com", password="SenhaForte!2026")
        form = RegisterForm(data={
            "username": "novo",
            "email": "dup@example.com",
            "password1": "OutraSenha!2026",
            "password2": "OutraSenha!2026",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)


class LoginFormTests(TestCase):
    def test_widgets_get_bootstrap_class(self):
        form = LoginForm()
        for field in form.fields.values():
            self.assertIn("form-control", field.widget.attrs["class"])


class RegisterViewTests(TestCase):
    def test_get_renders_form(self):
        response = self.client.get(reverse("accounts:register"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Criar conta")

    def test_post_valid_creates_and_logs_in_user(self):
        response = self.client.post(reverse("accounts:register"), {
            "username": "anderson",
            "email": "anderson@example.com",
            "password1": "SenhaForte!2026",
            "password2": "SenhaForte!2026",
        })
        self.assertRedirects(response, reverse("tasks:dashboard"))
        self.assertTrue(User.objects.filter(username="anderson").exists())
        self.assertIn("_auth_user_id", self.client.session)

    def test_password_is_hashed_not_plaintext(self):
        self.client.post(reverse("accounts:register"), {
            "username": "anderson",
            "email": "anderson@example.com",
            "password1": "SenhaForte!2026",
            "password2": "SenhaForte!2026",
        })
        user = User.objects.get(username="anderson")
        self.assertNotEqual(user.password, "SenhaForte!2026")
        self.assertTrue(user.password.startswith("argon2$"))
        self.assertTrue(user.check_password("SenhaForte!2026"))

    def test_post_invalid_shows_errors(self):
        response = self.client.post(reverse("accounts:register"), {
            "username": "anderson",
            "email": "nao-e-um-email",
            "password1": "SenhaForte!2026",
            "password2": "outra-senha",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="anderson").exists())


class LoginLogoutViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="anderson", email="anderson@example.com", password="SenhaForte!2026"
        )

    def test_get_renders_form(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)

    def test_login_success_redirects_and_messages(self):
        response = self.client.post(reverse("accounts:login"), {
            "username": "anderson", "password": "SenhaForte!2026",
        }, follow=True)
        self.assertIn("_auth_user_id", self.client.session)
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("Bem-vindo" in m for m in messages))

    def test_login_wrong_password_stays_on_form(self):
        response = self.client.post(reverse("accounts:login"), {
            "username": "anderson", "password": "errada",
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_authenticated_user_is_redirected_away_from_login(self):
        self.client.login(username="anderson", password="SenhaForte!2026")
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 302)

    def test_logout(self):
        self.client.login(username="anderson", password="SenhaForte!2026")
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("core:landing"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_dashboard_requires_login_redirect(self):
        response = self.client.get(reverse("tasks:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
