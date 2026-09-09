"""Campos de model com criptografia transparente em repouso."""

from django.db import models

from core.crypto import decrypt_text, encrypt_text


class EncryptedTextField(models.TextField):
    """TextField que é criptografado antes de ir para o banco e
    descriptografado ao ser lido de volta para o Python.

    O valor nunca fica em texto plano na tabela — útil para notas de
    tarefas ou qualquer conteúdo sensível do usuário.
    """

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return decrypt_text(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        return encrypt_text(value)
