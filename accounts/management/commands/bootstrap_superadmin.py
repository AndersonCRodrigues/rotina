from decouple import config
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from accounts.models import User


class Command(BaseCommand):
    help = "Cria o superadmin configurado no ambiente."

    def handle(self, *args, **options):
        email = config("SUPERADMIN_EMAIL", default="").strip().lower()
        password = config("SUPERADMIN_PASSWORD", default="")

        if not email and not password:
            return
        if not email or not password:
            raise CommandError("Defina SUPERADMIN_EMAIL e SUPERADMIN_PASSWORD juntos.")

        existing = User.objects.filter(email__iexact=email).first()
        if existing is not None:
            self.check_superadmin(existing)
            return

        user = User(username=email, email=email)
        try:
            user.clean_fields(exclude=["password"])
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error

        try:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": email,
                    "password": make_password(password),
                    "is_staff": True,
                    "is_superuser": True,
                },
            )
        except IntegrityError as error:
            raise CommandError(
                "O e-mail configurado já está em uso como nome de usuário."
            ) from error

        self.check_superadmin(user)
        if created:
            self.stdout.write(self.style.SUCCESS("Superadmin criado."))

    def check_superadmin(self, user):
        if not (user.is_superuser and user.is_staff and user.is_active):
            raise CommandError(
                "O e-mail configurado pertence a uma conta que não é um superadmin ativo."
            )
