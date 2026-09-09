from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("cadastro/", views.RegisterView.as_view(), name="register"),
    path("login/", views.AccountLoginView.as_view(), name="login"),
    path("logout/", views.AccountLogoutView.as_view(), name="logout"),
]
