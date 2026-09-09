from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.urls import reverse

from core import crypto
from core.fields import EncryptedTextField


class CryptoUtilTests(TestCase):
    def tearDown(self):
        # evita que o cache de _fernet vaze configuração entre testes
        crypto._fernet.cache_clear()

    def test_encrypt_and_decrypt_roundtrip(self):
        token = crypto.encrypt_text("dado sensível")
        self.assertNotEqual(token, "dado sensível")
        self.assertEqual(crypto.decrypt_text(token), "dado sensível")

    def test_encrypt_text_none_passthrough(self):
        self.assertIsNone(crypto.encrypt_text(None))

    def test_decrypt_text_none_passthrough(self):
        self.assertIsNone(crypto.decrypt_text(None))

    def test_decrypt_text_empty_string_passthrough(self):
        self.assertEqual(crypto.decrypt_text(""), "")

    def test_decrypt_text_invalid_token_returns_empty_string(self):
        self.assertEqual(crypto.decrypt_text("token-invalido-corrompido"), "")

    def test_fernet_raises_when_key_not_configured(self):
        crypto._fernet.cache_clear()
        with override_settings(FIELD_ENCRYPTION_KEY=""):
            with self.assertRaises(ImproperlyConfigured):
                crypto.encrypt_text("qualquer coisa")
        crypto._fernet.cache_clear()


class EncryptedTextFieldTests(TestCase):
    def setUp(self):
        self.field = EncryptedTextField()

    def test_from_db_value_none(self):
        self.assertIsNone(self.field.from_db_value(None, None, None))

    def test_from_db_value_decrypts(self):
        token = crypto.encrypt_text("segredo")
        self.assertEqual(self.field.from_db_value(token, None, None), "segredo")

    def test_get_prep_value_none(self):
        self.assertIsNone(self.field.get_prep_value(None))

    def test_get_prep_value_empty_string(self):
        self.assertEqual(self.field.get_prep_value(""), "")

    def test_get_prep_value_encrypts(self):
        prepped = self.field.get_prep_value("segredo")
        self.assertNotEqual(prepped, "segredo")
        self.assertEqual(crypto.decrypt_text(prepped), "segredo")


class LandingPageTests(TestCase):
    def test_landing_page_loads(self):
        response = self.client.get(reverse("core:landing"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rotina")
