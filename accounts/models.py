from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Usuário customizado (mesmo sem novos campos ainda, é boa prática
    do Django começar todo projeto com AUTH_USER_MODEL próprio — trocar
    depois exige migração dolorosa de banco em produção).
    """

    email = models.EmailField("e-mail", unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        return self.username
