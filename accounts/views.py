from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import CreateView

from accounts.forms import LoginForm, RegisterForm


class RegisterView(CreateView):
    """Cadastro de novo usuário. Em caso de sucesso, autentica
    automaticamente (evita fricção de pedir login logo após cadastro).
    """

    form_class = RegisterForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("tasks:dashboard")

    def form_valid(self, form):
        response = super().form_valid(form)
        auth_login(self.request, self.object)
        messages.success(self.request, "Conta criada com sucesso. Bem-vindo(a)!")
        return response


class AccountLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        messages.success(self.request, f"Bem-vindo(a) de volta, {form.get_user().username}!")
        return super().form_valid(form)


class AccountLogoutView(LogoutView):
    next_page = reverse_lazy("core:landing")
