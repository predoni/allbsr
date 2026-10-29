from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import services
from .models import AuthToken, CompanyDetails, User, UserDetails
from .permissions import IsAdmin, IsSelfOrReadOnly, OwnsDetailsOrReadOnly
from .serializer import (
    CompanyDetailsSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    UserDetailsSerializer,
    UserSerializer,
)

# Create your views here.

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]  # registration must work without a token
        if self.action == 'reset_password':
            return [IsAuthenticated(), IsAdmin()]
        return [IsAuthenticated(), IsSelfOrReadOnly()]

    # @action adds an extra route on the viewset: POST /users/<id>/reset-password/
    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        """Admin-only: start the reset process for any user."""
        token = services.start_password_reset(self.get_object())
        return Response({
            'detail': 'Password invalidated; a reset token was emailed to the user.',
            'token': token.key,  # so the admin can also pass it on directly
        })


class UserDetailsViewSet(viewsets.ModelViewSet):
    queryset = UserDetails.objects.all()
    serializer_class = UserDetailsSerializer
    permission_classes = [IsAuthenticated, OwnsDetailsOrReadOnly]


class CompanyDetailsViewSet(viewsets.ModelViewSet):
    queryset = CompanyDetails.objects.all()
    serializer_class = CompanyDetailsSerializer
    permission_classes = [IsAuthenticated, OwnsDetailsOrReadOnly]

class LoginView(APIView):
    """POST {email, password} -> {token, user}"""
    authentication_classes = []  # nobody is logged in yet when they call this
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'  # rate defined in settings.REST_FRAMEWORK

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # -> 400 with the error message
        user = serializer.validated_data['user']
        token, _ = AuthToken.objects.get_or_create(user=user)
        return Response({'token': token.key, 'user': UserSerializer(user).data})


class LogoutView(APIView):
    """POST with `Authorization: Token <key>` -> deletes that token."""
    def post(self, request):
        request.auth.delete()  # request.auth is the AuthToken instance
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """GET with `Authorization: Token <key>` -> the current user."""
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class PasswordResetRequestView(APIView):
    """POST {email} -> starts the reset process for that account (self-service)."""
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset'

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email=serializer.validated_data['email']).first()
        if user is not None:
            services.start_password_reset(user)
        # Same reply either way, so this endpoint can't be used to probe for accounts.
        return Response({'detail': 'If that account exists, a reset token has been emailed to it.'})


class PasswordResetConfirmView(APIView):
    """POST {token, new_password} -> completes the reset process."""
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset_confirm'

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.complete_password_reset(
            serializer.validated_data['token'], serializer.validated_data['new_password']
        )
        return Response({'detail': 'Password updated. You can now log in.'})


class AdminDashboardView(APIView):
    """GET -> overview for admins: totals plus every user with their details."""
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        users = User.objects.select_related('details', 'company_details').order_by('email')
        return Response({
            'totals': {
                'users': users.count(),
                'individuals': users.filter(is_company=False).count(),
                'companies': users.filter(is_company=True).count(),
                'admins': users.filter(is_admin=True).count(),
            },
            'users': UserSerializer(users, many=True).data,
        })
