from django.urls import path, include
from .users.views import UserViewSet, UserDetailsViewSet, CompanyDetailsViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'user-details', UserDetailsViewSet)
router.register(r'company-details', CompanyDetailsViewSet)

urlpatterns = [
    path('api/users/', include(router.urls)),
]