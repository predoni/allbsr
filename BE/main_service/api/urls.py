from django.urls import path, include
from .users.views import (
    AdminDashboardView,
    CompanyDetailsViewSet,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    UserDetailsViewSet,
    UserViewSet,
)
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'user-details', UserDetailsViewSet)
router.register(r'company-details', CompanyDetailsViewSet)

urlpatterns = [
    path('api/users/login/', LoginView.as_view(), name='login'),
    path('api/users/logout/', LogoutView.as_view(), name='logout'),
    path('api/users/me/', MeView.as_view(), name='me'),
    path('api/users/password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('api/users/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('api/users/admin/dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('api/users/', include(router.urls)),
]