from django.db import IntegrityError, transaction
from rest_framework import serializers, status
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.forms import RegisterForm


class RegistrationInput(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.CharField()
    password1 = serializers.CharField(trim_whitespace=False)
    password2 = serializers.CharField(trim_whitespace=False)


class RegistrationView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        data = RegistrationInput(data=request.data)
        data.is_valid(raise_exception=True)
        form = RegisterForm(data.validated_data)
        if not form.is_valid():
            raise serializers.ValidationError(dict(form.errors))

        try:
            with transaction.atomic():
                user = form.save()
        except IntegrityError as error:
            raise serializers.ValidationError(
                "O nome de usuário ou e-mail informado já está em uso."
            ) from error

        return Response(
            {"id": user.pk, "username": user.username, "email": user.email},
            status=status.HTTP_201_CREATED,
        )


class TokenLoginView(ObtainAuthToken):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "api_login"


class TokenLogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.auth.delete()
        return Response(status=204)


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({"id": user.pk, "username": user.username, "email": user.email})
